from __future__ import absolute_import, division, print_function

import sys,os
from libtbx.utils import Sorry
from cctbx.array_family import flex
from copy import deepcopy
from libtbx import group_args
from libtbx.utils import null_out

from cctbx.array_family import flex
import scitbx.lbfgs
import math
from cctbx.maptbx.segment_and_split_map import map_and_b_object
from six.moves import range
from six.moves import zip
from scitbx import matrix

def write_mtz(ma=None,phases=None,file_name=None):
  mtz_dataset=ma.as_mtz_dataset(column_root_label="FWT")
  mtz_dataset.add_miller_array(miller_array=phases,column_types="P", column_root_label="PHWT")
  mtz_dataset.mtz_object().write(file_name=file_name)

# XXX copied these from cctbx.miller; made small change to catch weird case
#  where normalizations are negative.  Just multiply these *-1 and it seems to
#  close to what we want. Figure this out later...
# XXX Also set means=1 not mean square = 1

def amplitude_quasi_normalisations(ma, d_star_power=1, set_to_minimum=None,
    pseudo_likelihood=False):  # Used for pseudo-likelihood calculation
    epsilons = ma.epsilons().data().as_double()
    mean_f_sq_over_epsilon = flex.double()
    for i_bin in ma.binner().range_used():
      sel = ma.binner().selection(i_bin)
      if pseudo_likelihood:
        sel_f_sq = flex.pow2(ma.data().select(sel)) # original method used
      else: # usual
        sel_f_sq = ma.data().select(sel)
      if (sel_f_sq.size() > 0):
        sel_epsilons = epsilons.select(sel)
        sel_f_sq_over_epsilon = sel_f_sq / sel_epsilons
        mean_f_sq_over_epsilon.append(flex.mean(sel_f_sq_over_epsilon))
      else:
        mean_f_sq_over_epsilon.append(0)
    mean_f_sq_over_epsilon_interp = ma.binner().interpolate(
      mean_f_sq_over_epsilon, d_star_power)
    if set_to_minimum and not mean_f_sq_over_epsilon_interp.all_gt(0):
      # HACK NO REASON THIS SHOULD WORK BUT IT GETS BY THE FAILURE
      sel = (mean_f_sq_over_epsilon_interp <= set_to_minimum)
      mean_f_sq_over_epsilon_interp.set_selected(sel,-mean_f_sq_over_epsilon_interp)
      sel = (mean_f_sq_over_epsilon_interp <= set_to_minimum)
      mean_f_sq_over_epsilon_interp.set_selected(sel,set_to_minimum)
    assert mean_f_sq_over_epsilon_interp.all_gt(0)
    from cctbx.miller import array
    return array(ma, flex.sqrt(mean_f_sq_over_epsilon_interp))
    # XXX was below before 2017-10-25
    # return array(ma, mean_f_sq_over_epsilon_interp)

def quasi_normalize_structure_factors(ma, d_star_power=1, set_to_minimum=None,
     pseudo_likelihood=False):
    normalisations = amplitude_quasi_normalisations(ma, d_star_power,
       set_to_minimum=set_to_minimum,pseudo_likelihood=pseudo_likelihood)
    if pseudo_likelihood:
      print("Norms:")
      for n,d in zip(normalisations[:100],ma.data()[:100]): print(n,d)

    q = ma.data() / normalisations.data()
    from cctbx.miller import array
    return array(ma, q)

def get_array(file_name=None,labels=None):

  print("Reading from %s" %(file_name))
  from iotbx import reflection_file_reader
  reflection_file = reflection_file_reader.any_reflection_file(
       file_name=file_name)
  array_to_use=None
  if labels:
    for array in reflection_file.as_miller_arrays():
      if ",".join(array.info().labels)==labels:
        array_to_use=array
        break
  else:
    for array in reflection_file.as_miller_arrays():
      if array.is_complex_array() or array.is_xray_amplitude_array() or\
          array.is_xray_intensity_array():
        array_to_use=array
        break
  if not array_to_use:
    text=""
    for array in reflection_file.as_miller_arrays():
      text+=" %s " %(",".join(array.info().labels))

    raise Sorry("Cannot identify array to use...possibilities: %s" %(text))

  print("Using the array %s" %(",".join(array_to_use.info().labels)))
  return array_to_use


def get_amplitudes(args):
  if not args or 'help' in args or '--help' in args:
    print("\nsharpen.py")
    print("Read in map coefficients or amplitudes and sharpen")
    return

  new_args=[]
  file_name=None
  for arg in args:
    if os.path.isfile(arg) and arg.endswith(".mtz"):
      file_name=arg
    else:
      new_args.append(arg)
  args=new_args
  labels=None

  array_list=[]

  array_list.append(get_array(file_name=file_name,labels=labels))
  array=array_list[-1]
  phases=None
  assert array.is_complex_array()
  return array


def get_effective_b_values(d_min_ratio=None,resolution_dependent_b=None,
    resolution=None):
  # Return effective b values at sthol2_1 2 and 3
  # see adjust_amplitudes_linear below

  d_min=resolution*d_min_ratio
  sthol2_2=0.25/resolution**2
  sthol2_1=sthol2_2*0.5
  sthol2_3=0.25/d_min**2
  b1=resolution_dependent_b[0]
  b2=resolution_dependent_b[1]
  b3=resolution_dependent_b[2]

  b3_use=b3+b2

  res_1=(0.25/sthol2_1)**0.5
  res_2=(0.25/sthol2_2)**0.5
  res_3=(0.25/sthol2_3)**0.5

  #  Scale factor is exp(b3_use) at res_3 for example
  #  f=exp(-b sthol2)
  #  b= - ln(f)/sthol2
  b1=-b1/sthol2_1
  b2=-b2/sthol2_2
  b3_use=-b3_use/sthol2_3


  return [res_1,res_2,res_3],[b1,b2,b3_use]

def adjust_amplitudes_linear(f_array,b1,b2,b3,resolution=None,
    d_min_ratio=None):
  # do something to the amplitudes.
  #   b1=delta_b at midway between d=inf and d=resolution,b2 at resolution,
  #   b3 at d_min (added to b2)
  # pseudo-B at position of b1= -b1/sthol2_2= -b1*4*resolution**2
  #  or...b1=-pseudo_b1/(4*resolution**2)
  #  typical values of say b1=1 at 3 A -> pseudo_b1=-4*9=-36

  data_array=f_array.data()
  sthol2_array=f_array.sin_theta_over_lambda_sq()
  scale_array=flex.double()
  import math
  #d_min=f_array.d_min()
  #if resolution is None: resolution=d_min
  d_min=d_min_ratio*resolution

  sthol2_2=0.25/resolution**2
  sthol2_1=sthol2_2*0.5
  sthol2_3=0.25/d_min**2
  b0=0.0
  d_spacings=f_array.d_spacings()
  b3_use=b3+b2
  for x,(ind,sthol2),(ind1,d) in zip(data_array,sthol2_array,d_spacings):
      if sthol2 > sthol2_2:
        value=b2+(sthol2-sthol2_2)*(b3_use-b2)/(sthol2_3-sthol2_2)
      elif sthol2 > sthol2_1:
        value=b1+(sthol2-sthol2_1)*(b2-b1)/(sthol2_2-sthol2_1)
      else:
        value=b0+(sthol2-0.)*(b1-b0)/(sthol2_1-0.)
      scale_array.append(math.exp(value))
  data_array=data_array*scale_array
  return f_array.customized_copy(data=data_array)

def get_model_map_coeffs_normalized(pdb_inp=None,
   si=None,
   f_array=None,
   overall_b=None,
   resolution=None,
   n_bins=None,
   target_b_iso_model_scale=0,
   target_b_iso_ratio = 5.9,  # empirical, see params for segment_and_split_map
   out=sys.stdout):
  if not pdb_inp: return None
  if not si:
    from cctbx.maptbx.segment_and_split_map import sharpening_info
    si=sharpening_info(resolution=resolution,
     target_b_iso_model_scale=0,
     target_b_iso_ratio = target_b_iso_ratio,
     n_bins=n_bins)
  # define Wilson B for the model
  if overall_b is None:
    if si.resolution:
      overall_b=si.get_target_b_iso()*si.target_b_iso_model_scale
    else:
      overall_b=0
    print("Setting Wilson B = %5.1f A" %(overall_b), file=out)

  # create model map using same coeffs
  from cctbx.maptbx.segment_and_split_map import get_f_phases_from_model
  try:
    model_map_coeffs=get_f_phases_from_model(
     pdb_inp=pdb_inp,
     f_array=f_array,
     overall_b=overall_b,
     k_sol=si.k_sol,
     b_sol=si.b_sol,
     out=out)
  except Exception as e:
    print ("Failed to get model map coeffs...going on",file=out)
    return None


  from cctbx.maptbx.segment_and_split_map import map_coeffs_as_fp_phi,get_b_iso
  model_f_array,model_phases=map_coeffs_as_fp_phi(model_map_coeffs)
  (d_max,d_min)=f_array.d_max_min(d_max_is_highest_defined_if_infinite=True)
  model_f_array.setup_binner(n_bins=si.n_bins,d_max=d_max,d_min=d_min)

  # Set overall_b....
  final_b_iso=get_b_iso(model_f_array,d_min=resolution)
  print("Effective b_iso of "+\
     "adjusted model map:  %6.1f A**2" %(final_b_iso), file=out)
  model_map_coeffs_normalized=model_f_array.phase_transfer(
     phase_source=model_phases,deg=True)
  return model_map_coeffs_normalized

def get_b_eff(si=None,out=sys.stdout):
  if si.rmsd is None:
    b_eff=None
  else:
    b_eff=8*3.14159*si.rmsd**2
    print("Setting b_eff for fall-off at %5.1f A**2 based on model error of %5.1f A" \
       %( b_eff,si.rmsd), file=out)
  return b_eff

def cc_fit(sthol_list=None,scale=None,value_zero=None,baseline=None,
     scale_using_last=None):
  # for scale_using_last, fix final value at zero
  fit=flex.double()
  s_zero=sthol_list[0]
  for s in sthol_list:
    fit.append(value_zero*math.exp(-scale*(s-s_zero)))
  if scale_using_last:
    fit=fit-fit[-1]
  return fit

def get_baseline(scale=None,scale_using_last=None,max_cc_for_rescale=None):
  if not scale_using_last:
    return 0
  else:
    baseline=min(0.99,max(0.,scale[-scale_using_last:].min_max_mean().mean))
    if baseline > max_cc_for_rescale:
       return None
    else:
       return baseline

def fit_cc(cc_list=None,sthol_list=None,
    scale_min=None,scale_max=None,n_tries=None,scale_using_last=None):
  # find value of scale in range scale_min,scale_max that minimizes rms diff
  # between cc_list and cc_list[0]*exp(-scale*(sthol-sthol_list[0]))
  # for scale_using_last, require it to go to zero at end

  best_scale=None
  best_rms=None
  for i in range(n_tries):
    scale=scale_min+(scale_max-scale_min)*i/n_tries
    fit=cc_fit(sthol_list=sthol_list,scale=scale,value_zero=cc_list[0],
       scale_using_last=scale_using_last)
    fit=fit-cc_list
    rms=fit.norm()
    if best_rms is None or rms<best_rms:
      best_rms=rms
      best_scale=scale
  return cc_fit(sthol_list=sthol_list,scale=best_scale,value_zero=cc_list[0],
      scale_using_last=scale_using_last)

def get_fitted_cc(cc_list=None,sthol_list=None, cc_cut=None,
   scale_using_last=None,keep_cutoff_point=False,force_scale_using_last=False,
   cutoff_after_last_high_point = False):
  # only do this if there is some value of s where cc is at least 2*cc_cut or
  #  (1-c_cut/2), whichever is smaller
  min_cc=min(2*cc_cut,1-0.5*cc_cut)
  if cc_list.min_max_mean().max < min_cc and (not force_scale_using_last):
    return cc_list
  # 2020-10-08 instead last point where cc >=cc_cut cutoff_after_last_high_point
  # find first point after point where cc>=min_cc that cc<=cc_cut
  #   then back off by 1 point  # 2019-10-12 don't back off if keep_cutoff_point
  found_high=False
  s_cut=None
  i_cut=0
  if (not cutoff_after_last_high_point):
    for s,cc in zip(sthol_list,cc_list):
      if cc > min_cc:
        found_high=True
      if found_high and cc < cc_cut:
        s_cut=s
        break
      i_cut+=1
  else:
    ii=0
    for s,cc in zip(sthol_list,cc_list):
      if cc > min_cc:
        found_high=True
      if found_high and cc >= cc_cut:
        s_cut = s
        i_cut = ii
      ii += 1

  if force_scale_using_last:
    scale_using_last=True
    s_cut=sthol_list[0]
    i_cut=1
  if s_cut is None or i_cut==0:
    return cc_list

  if keep_cutoff_point:
    i_cut=max(1,i_cut-1)

  #Fit remainder
  sthol_remainder_list=sthol_list[i_cut:]
  cc_remainder_list=cc_list[i_cut:]
  n=cc_remainder_list.size()
  scale_min=10 # soft
  scale_max=500 # hard
  n_tries=200

  fitted_cc_remainder_list=fit_cc(
     cc_list=cc_remainder_list,sthol_list=sthol_remainder_list,
     scale_min=scale_min,scale_max=scale_max,n_tries=n_tries,
     scale_using_last=scale_using_last)

  new_cc_list=cc_list[:i_cut]
  new_cc_list.extend(fitted_cc_remainder_list)
  return new_cc_list

def estimate_cc_star(cc_list=None,sthol_list=None, cc_cut=None,
    scale_using_last=None,
    keep_cutoff_point=False):
  # cc ~ sqrt(2*half_dataset_cc/(1+half_dataset_cc))
  # however for small cc the errors are very big and we think cc decreases
  #  rapidly towards zero once cc is small
  # So find value of sthol_zero that gives cc about cc_cut...for
  #   sthol >sthol_zero use fit of cc_zero * exp(-falloff*(sthol-sthol_zero))
  #  for scale_using_last set: subtract off final values so it goes to zero.

  fitted_cc=get_fitted_cc(
    cc_list=cc_list,sthol_list=sthol_list,cc_cut=cc_cut,
    scale_using_last=scale_using_last,
    keep_cutoff_point=keep_cutoff_point)

  cc_star_list=flex.double()
  for cc in fitted_cc:
     cc=max(cc,0.)
     cc_star=(2.*cc/(1.+cc))**0.5
     cc_star_list.append(cc_star)
  return cc_star_list


def rescale_cc_list(cc_list=None,scale_using_last=None,
    max_cc_for_rescale=None):
  baseline=get_baseline(scale=cc_list,
      scale_using_last=scale_using_last,
      max_cc_for_rescale=max_cc_for_rescale)
  if baseline is None:
     return cc_list,baseline

  # replace cc with (cc-baseline)/(1-baseline)
  scaled_cc_list=flex.double()
  for cc in cc_list:
    scaled_cc_list.append((cc-baseline)/(1-baseline))
  return scaled_cc_list,baseline

def get_calculated_scale_factors(
      sthol_list=None,
      effective_b=None,
      b_zero = None,
      cc_list = None,
      dv = None,
      uc = None):
    recip_space_vectors = flex.vec3_double()
    scale_values = flex.double()
    original_scale_values = flex.double()
    indices = flex.miller_index()
    if effective_b is None and not cc_list:
      #no info
      return group_args(
        indices = indices,
        scale_values = scale_values,
        original_scale_values = original_scale_values)

    for s,cc in zip(sthol_list,cc_list):
      d = 1/s
      sthol2 = 0.25/d**2
      recip_space_vectors.append(matrix.col(dv) * s)
      if effective_b is not None:
        scale_values.append(b_zero*math.exp (max(-20.,min(20.,
         -effective_b * sthol2))))
      else:
        scale_values.append(cc)

      original_scale_values.append(cc)
    indices = flex.miller_index(tuple(get_nearest_lattice_points(
        uc,recip_space_vectors)))
    return group_args(
      indices = indices,
      scale_values = scale_values,
      original_scale_values = original_scale_values)

def calculate_fsc(si=None,
     f_array=None,  # just used for binner
     map_coeffs=None,
     model_map_coeffs=None,
     external_map_coeffs=None,
     first_half_map_coeffs=None,
     second_half_map_coeffs=None,
     resolution=None,
     fraction_complete=None,
     min_fraction_complete=None,
     is_model_based=None,
     cc_cut=None,
     scale_using_last=None,
     max_cc_for_rescale=None,
     pseudo_likelihood=False,
     skip_scale_factor=False,
     equalize_power=False,
     verbose=None,
     rmsd_resolution_factor = 0.25,  # empirical, see params for segment_and_split_map
     maximum_scale_factor = None, # limit on size
     optimize_b_eff = None,
     low_res_bins = 3,
     direction_vector = None,
     direction_vectors = None,
     smooth_fsc = None,
     cutoff_after_last_high_point = None,
     get_scale_as_aniso_u = None,
     expected_rms_fc_list = None,
     out=sys.stdout):

  '''
    Calculate FSC of 2 maps and estimate scale factors
    If direction_vector or direction_vectors supplied, calculate
     CC values weighted by abs() component along direction vector
    If list of direction vectors, return group_args with si objects
  '''

  # calculate anticipated fall-off of model data with resolution
  if si.rmsd is None and is_model_based:
    if not rmsd_resolution_factor:
      rmsd_resolution_factor = si.rmsd_resolution_factor
    if not resolution:
      resolution = si.resolution
    si.rmsd=resolution*rmsd_resolution_factor
    print("Setting rmsd to %5.1f A based on resolution of %5.1f A" %(
       si.rmsd,resolution), file=out)
  elif is_model_based:
    if not resolution:
      resolution = si.resolution
    print("RMSD is %5.1f A and resolution is %5.1f A" %(
       si.rmsd,resolution), file=out)

  # get f and model_f vs resolution and FSC vs resolution and apply

  # If external_map_coeffs then simply scale f to external_map_coeffs

  # scale to f_array and return sharpened map
  dsd = f_array.d_spacings().data()
  from cctbx.maptbx.segment_and_split_map import map_coeffs_to_fp

  if is_model_based:
    mc1=map_coeffs
    mc2=model_map_coeffs
    fo_map=map_coeffs # scale map_coeffs to model_map_coeffs*FSC
    fc_map=model_map_coeffs
    b_eff=get_b_eff(si=si,out=out)
  elif external_map_coeffs:
    mc1=map_coeffs
    mc2=external_map_coeffs
    fo_map=map_coeffs # scale map_coeffs to external_map_coeffs
    fc_map=external_map_coeffs
    b_eff=None

  else: # half_dataset
    mc1=first_half_map_coeffs
    mc2=second_half_map_coeffs
    fo_map=map_coeffs # scale map_coeffs to cc*
    fc_map=model_map_coeffs
    b_eff=None


  ratio_list=flex.double()
  target_sthol2=flex.double()
  sthol_list=flex.double()
  d_min_list=flex.double()
  rms_fo_list=flex.double()
  rms_fc_list=flex.double()
  max_possible_cc=None
  n_list = flex.double()

  if direction_vectors:
    pass # already ok
  elif direction_vector:
    direction_vectors = [direction_vector]
  else:
    direction_vectors = [None]

  cc_dict_by_dv = {}
  rms_fo_dict_by_dv = {}
  rms_fc_dict_by_dv = {}
  ratio_dict_by_dv = {}
  i = 0
  for dv in direction_vectors:
    cc_dict_by_dv [i] = flex.double()
    rms_fo_dict_by_dv [i] = flex.double()
    rms_fc_dict_by_dv [i] = flex.double()
    ratio_dict_by_dv [i] = flex.double()
    i += 1

  first_bin =True
  weights_para_list = [] # NOTE: this makes N * f_array.size() arrays!!
  for dv in direction_vectors:
    if dv:
      weights_para_list.append(
        get_normalized_weights_para(f_array,direction_vectors, dv,
          include_all_in_lowest_bin = True))
    else:
      weights_para_list.append(None)

  for i_bin in f_array.binner().range_used():
    sel       = f_array.binner().selection(i_bin)
    d         = dsd.select(sel)
    if d.size()<1:
      raise Sorry("Please reduce number of bins (no data in bin "+
        "%s) from current value of %s" %(i_bin,f_array.binner().n_bins_used()))
    d_min     = flex.min(d)
    d_max     = flex.max(d)
    d_avg     = flex.mean(d)
    n         = d.size()
    m1        = mc1.select(sel)
    m2        = mc2.select(sel)

    cc = None
    i = 0
    if fc_map:
      fc        = fc_map.select(sel)
    else:
      fc = None
    if fo_map:
          fo        = fo_map.select(sel)
    else:
      fo = None

    for dv, weights_para in zip(direction_vectors, weights_para_list):
      if dv:
        weights_para_sel = weights_para.select(sel)
        weights_para_sel_sqrt = flex.sqrt(weights_para_sel)
        m1a=m1.customized_copy(data = m1.data() * weights_para_sel_sqrt)
        m2a=m2.customized_copy(data = m2.data() * weights_para_sel_sqrt)
        cca        = m1a.map_correlation(other = m2a)
        if cca is None:
          cca=0.
        cc_dict_by_dv[i].append(cca)
        normalization = 1./max(1.e-10,weights_para_sel.norm())
        if fo_map:
          fo_a = fo.customized_copy(data=fo.data()*weights_para_sel)
          f_array_fo=map_coeffs_to_fp(fo_a)
          rms_fo=normalization * f_array_fo.data().norm()
        else:
          rms_fo=1.

        if expected_rms_fc_list:
          rms_fc = expected_rms_fc_list[i_bin-1]
        elif fc_map:
          fc_a  = fc.customized_copy(data=fc.data()*weights_para_sel)
          f_array_fc=map_coeffs_to_fp(fc_a)
          rms_fc=normalization *f_array_fc.data().norm()
        else:
          rms_fc=1.

        rms_fo_dict_by_dv[i].append(rms_fo)
        rms_fc_dict_by_dv[i].append(rms_fc)
        ratio_dict_by_dv[i].append(max(1.e-10,rms_fc)/max(1.e-10,rms_fo))

        i += 1
        if (cca is not None) and (cc is None):
          cc = cca # save first one
      else:
        cc        = m1.map_correlation(other = m2)
        if external_map_coeffs: # only for no direction vectors
          cc=1.
        if cc is None:
          cc= 0
        cc_dict_by_dv[i].append(cc)
        if fo_map:
          f_array_fo=map_coeffs_to_fp(fo)
          rms_fo=f_array_fo.data().norm()
        else:
          rms_fo=1.

        if expected_rms_fc_list:
          rms_fc = expected_rms_fc_list[i_bin-1]
        elif fc_map:
          f_array_fc=map_coeffs_to_fp(fc)
          rms_fc=f_array_fc.data().norm()
        else:
          rms_fc=1.
        rms_fo_dict_by_dv[i].append(rms_fo)
        rms_fc_dict_by_dv[i].append(rms_fc)
        ratio_dict_by_dv[i].append(max(1.e-10,rms_fc)/max(1.e-10,rms_fo))

    sthol2=0.25/d_avg**2 # note this is 0.25 * sthol**2 .... not consistent
    target_sthol2.append(sthol2)
    sthol_list.append(1/d_avg)
    d_min_list.append(d_min)
    n_list.append(m1.size())


    if b_eff is not None:
      max_cc_estimate=cc* math.exp(min(20.,sthol2*b_eff))
    else:
      max_cc_estimate=cc
    max_cc_estimate=max(0.,min(1.,max_cc_estimate))
    if max_possible_cc is None or (
        max_cc_estimate > 0 and max_cc_estimate > max_possible_cc):
      max_possible_cc=max_cc_estimate
    if verbose:
      print("d_min: %5.1f  FC: %7.1f  FOBS: %7.1f   CC: %5.2f" %(
      d_avg,rms_fc,rms_fo,cc), file=out)
    first_bin = False

  input_info = group_args(
     f_array = f_array,
     n_list = n_list,
     target_sthol2 = target_sthol2,
     d_min_list = d_min_list,
     pseudo_likelihood = pseudo_likelihood,
     equalize_power = equalize_power,
     is_model_based = is_model_based,
     skip_scale_factor = skip_scale_factor,
     maximum_scale_factor = maximum_scale_factor,
     out = out)

  # Now apply analyses on each cc_list (if more than one)
  si_list = []
  for i in range(len(direction_vectors)):
    if smooth_fsc:
      ratio_list = remove_values_if_necessary(ratio_dict_by_dv[i])
      rms_fo_list = remove_values_if_necessary(rms_fo_dict_by_dv[i])
      rms_fc_list = remove_values_if_necessary(rms_fc_dict_by_dv[i])
      cc_list = smooth_values(cc_dict_by_dv[i])
    else:
      ratio_list = remove_values_if_necessary(ratio_dict_by_dv[i])
      rms_fo_list = remove_values_if_necessary(rms_fo_dict_by_dv[i])
      rms_fc_list = remove_values_if_necessary(rms_fc_dict_by_dv[i])
      cc_list = cc_dict_by_dv[i]
    if len(direction_vectors) > 1:
      working_si = deepcopy(si)
      dv = direction_vectors[i]
    else:
      dv = None
      working_si = si  # so we can modify it in place
    working_si = complete_cc_analysis(
       dv,
       cc_list,
       rms_fc_list,
       rms_fo_list,
       ratio_list,
       scale_using_last,
       max_cc_for_rescale,
       optimize_b_eff,
       is_model_based,
       sthol_list,
       cc_cut,
       max_possible_cc,
       fraction_complete,
       min_fraction_complete,
       low_res_bins,
       working_si,
       b_eff,
       input_info,
       cutoff_after_last_high_point,
       get_scale_as_aniso_u,
       expected_rms_fc_list,
       out)
    si_list.append(working_si)
  if direction_vectors == [None]:
    return si_list[0]
  else:


    if get_scale_as_aniso_u:  # get the final scale factors as aniso_u

      if fo_map:
        # Calculate anisotropic scale factor to make Fo uniform
        # Decide on resolution based on rms_fo_list values
        resolution_for_aniso = get_resolution_for_aniso(sthol_list=sthol_list,
          si_list=si_list, minimum_ratio = 0.05)
        if not resolution_for_aniso:
          resolution_for_aniso = resolution

        f_array_fo=map_coeffs_to_fp(fo_map)
        f_array_fo_scaled,aniso_obj=analyze_aniso(
          b_iso=0,
          f_array=f_array_fo,resolution=resolution_for_aniso,
          remove_aniso=True,out=null_out())

        # Now normalize to fc_map if present and not setting targets externally
        if fc_map and (not expected_rms_fc_list):
          f_array_fc=map_coeffs_to_fp(fc_map)
          f_array_fc_scaled,fc_aniso_obj=analyze_aniso(
            b_iso=0,
            f_array=f_array_fc,resolution=resolution_for_aniso,
            remove_aniso=True,out=null_out())
        else:
          fc_aniso_obj = get_aniso_obj_from_direction_vectors(
            f_array = f_array,
            resolution = resolution,
            direction_vectors = direction_vectors,
            expected_rms_fc_list = expected_rms_fc_list,
            sthol_list = sthol_list)

        from cctbx import adptbx
        if fc_aniso_obj and fc_aniso_obj.b_cart:
          starting_fc_u_cart = adptbx.b_as_u(fc_aniso_obj.b_cart)
        else:
          starting_fc_u_cart = None
        if aniso_obj.b_cart:
          starting_u_cart = adptbx.b_as_u(aniso_obj.b_cart)
          if starting_fc_u_cart:
            starting_u_cart = tuple(matrix.col(starting_u_cart) -
             matrix.col(starting_fc_u_cart))
        else:
          starting_u_cart = None
      else:
        starting_u_cart = None

      aniso_obj = get_aniso_obj_from_direction_vectors(
        f_array = f_array,
        resolution = resolution,
        direction_vectors = direction_vectors,
        si_list = si_list,
        sthol_list = sthol_list)

      if aniso_obj.b_cart and starting_u_cart and \
         tuple(starting_u_cart) != (0,0,0,0,0,0):
        from cctbx import adptbx
        scaling_u_cart = adptbx.b_as_u(aniso_obj.b_cart)
        # U_cart to remove is starting_u_cart - scaling_u_cart
        overall_u_cart_to_remove = tuple(
          matrix.col(starting_u_cart) - matrix.col(scaling_u_cart))
      else: # failed...keep original
        overall_u_cart_to_remove = tuple((0,0,0,0,0,0))
        scaling_u_cart = starting_u_cart

    else:
      overall_u_cart_to_remove = None
      starting_u_cart = None
      scaling_u_cart = None

    return group_args(
     group_args_type = 'scaling_info objects, one set per direction_vector',
     direction_vectors = direction_vectors,
     scaling_info_list = si_list,
     overall_u_cart_to_remove = overall_u_cart_to_remove,
     starting_u_cart = starting_u_cart,
     scaling_u_cart = scaling_u_cart)


def get_aniso_obj_from_direction_vectors(
        f_array = None,
        resolution = None,
        direction_vectors = None,
        si_list = None,
        sthol_list = None,
        expected_rms_fc_list = None,
        invert_in_scaling = False,
        ):

      scale_values = flex.double()
      indices = flex.miller_index()
      extra_b = -15.  # Just so ml scaling gives about the right answer for
                # constant number that are not really reflection data
      if not si_list:
        si_list = []
        for dv in direction_vectors:
          si_list.append(group_args(
            effective_b = None,
            effective_b_f_obs = None,
            b_zero = 0,
            cc_list =expected_rms_fc_list,
           ))

      for dv,si in zip(direction_vectors,si_list):
        info = get_calculated_scale_factors(
          sthol_list=sthol_list,
          effective_b=(None if (si.effective_b is None) else (si.effective_b + extra_b)),  # so xtriage gives about right
          b_zero = si.b_zero,
          cc_list = si.cc_list,
          dv = dv,
          uc = f_array.unit_cell(),
           )
        indices.extend(info.indices)
        scale_values.extend(info.scale_values)

      if invert_in_scaling:
        scale_values = 1/scale_values
      scale_values_array = f_array.customized_copy(
        data = scale_values,
        indices = indices)

      scaled_array,aniso_obj=analyze_aniso(
        b_iso=0,
        invert = invert_in_scaling,
        f_array=scale_values_array,resolution=resolution,
        remove_aniso=True,out=null_out())
      return aniso_obj

def get_resolution_for_aniso(sthol_list=None, si_list=None,
    minimum_ratio = 0.05):
  highest_d_min = None
  for si in si_list:
    first_rms_fo = None
    for rms_fo,sthol in  zip(si.rms_fo_list,sthol_list):
      d = 1/sthol
      if first_rms_fo is None:
        first_rms_fo = rms_fo
      else:
        ratio = rms_fo/max(1.e-10, first_rms_fo)
        if ratio < minimum_ratio and (
            highest_d_min is None or d > highest_d_min):
          highest_d_min = d
  return highest_d_min

def remove_values_if_necessary(f_values,max_ratio=100, min_ratio=0.01):
  # Make sure values are within a factor of 100 of low_res ones...if they are
  #  not it was probably something like zero values or near-zero values
  f_values=flex.double(f_values)
  low_res = f_values[:3].min_max_mean().mean
  new_values=flex.double()
  last_value = low_res
  for x in f_values:
    if x > max_ratio * low_res or x < min_ratio * low_res:
      new_values.append(last_value)
    else:
      new_values.append(x)
      last_value = x
  return new_values

def smooth_values(cc_values, max_relative_rms=10, n_smooth = None,
    skip_first_frac = 0.1): # normally do not smooth the very first ones
  skip_first = max (1, int(0.5+skip_first_frac*cc_values.size()))

  if n_smooth:
    # smooth with window of n_smooth
    new_cc_values = flex.double()
    for i in range(cc_values.size()):
      if i < skip_first:
        new_cc_values.append(cc_values[i])
      else:
        sum=0.
        sum_n=0.
        for j in range(-n_smooth, n_smooth+1):
          weight = 1/(1+(abs(j)/n_smooth)) # just less as we go out
          k = i+j
          if k < 0 or k >= cc_values.size(): continue
          sum += cc_values[k] * weight
          sum_n += weight
        new_cc_values.append(sum/max(1.e-10,sum_n))
    return new_cc_values

  # Smooth values in cc_values  max_relative_rms is avg rms / avg delta
  if relative_rms(cc_values) <= max_relative_rms:
    return cc_values
  for i in range(1,cc_values.size()//2):
    smoothed_cc_values=smooth_values(cc_values,n_smooth=i)
    if relative_rms(smoothed_cc_values) <= max_relative_rms:
      return smoothed_cc_values
  smoothed_cc_values=smooth_values(cc_values,n_smooth=cc_values.size()//2)
  return smoothed_cc_values


def relative_rms(cc_values):
  diffs = cc_values[:-1] - cc_values[1:]
  avg_delta = abs(diffs.min_max_mean().mean)
  rms = diffs.standard_deviation_of_the_sample()
  return rms/max(1.e-10,avg_delta)

def complete_cc_analysis(
       direction_vector,
       cc_list,
       rms_fc_list,
       rms_fo_list,
       ratio_list,
       scale_using_last,
       max_cc_for_rescale,
       optimize_b_eff,
       is_model_based,
       sthol_list,
       cc_cut,
       max_possible_cc,
       fraction_complete,
       min_fraction_complete,
       low_res_bins,
       si,
       b_eff,
       input_info,
       cutoff_after_last_high_point,
       get_scale_as_aniso_u,
       expected_rms_fc_list,
       out):


  if scale_using_last: # rescale to give final value average==0
    cc_list,baseline=rescale_cc_list(
       cc_list=cc_list,scale_using_last=scale_using_last,
       max_cc_for_rescale=max_cc_for_rescale)
    if baseline is None: # don't use it
      scale_using_last=None


  original_cc_list=deepcopy(cc_list)
  if is_model_based: # jut smooth cc if nec
    fitted_cc=get_fitted_cc(
      cc_list=cc_list,sthol_list=sthol_list,cc_cut=cc_cut,
      scale_using_last=scale_using_last,
      cutoff_after_last_high_point = cutoff_after_last_high_point,)
    cc_list=fitted_cc
    text=" FIT "
  else:
    cc_list=estimate_cc_star(cc_list=cc_list,sthol_list=sthol_list,
      cc_cut=cc_cut,scale_using_last=scale_using_last)
    text=" CC* "

  if not max_possible_cc:
    max_possible_cc=0.01
  if si.target_scale_factors: # not using these
    max_possible_cc=1.
    fraction_complete=1.
  elif (not is_model_based):
    max_possible_cc=1.
    fraction_complete=1.
  else:
    # Define overall CC based on model completeness (CC=sqrt(fraction_complete))

    if fraction_complete is None:
      fraction_complete=max_possible_cc**2

      print(
     "Estimated fraction complete is %5.2f based on low_res CC of %5.2f" %(
          fraction_complete,max_possible_cc), file=out)
    else:
      print(
      "Using fraction complete value of %5.2f "  %(fraction_complete), file=out)
      max_possible_cc=fraction_complete**0.5

  if optimize_b_eff and is_model_based:
    ''' Find b_eff that maximizes expected map-model-cc to model with B=0'''
    best_b_eff = b_eff
    best_weighted_cc = get_target_scale_factors(
      cc_list=cc_list,
      rms_fo_list=rms_fo_list,
      ratio_list=ratio_list,
      b_eff=b_eff,
      max_possible_cc=max_possible_cc,
      **input_info()).weighted_cc
    for i in range(20):
      b_eff_working = 0.1 * i * b_eff
      weighted_cc=get_target_scale_factors(
         cc_list=cc_list,
         rms_fo_list=rms_fo_list,
         ratio_list=ratio_list,
         b_eff = b_eff_working,
         max_possible_cc=max_possible_cc,
         **input_info()).weighted_cc
      if weighted_cc > best_weighted_cc:
        best_b_eff = b_eff_working
        best_weighted_cc = weighted_cc
    print("Optimized effective B value: %.3f A**2 " %(best_b_eff),file=out)
    b_eff = best_b_eff

  info = get_target_scale_factors(
      cc_list=cc_list,
      rms_fo_list=rms_fo_list,
      ratio_list=ratio_list,
      b_eff=b_eff,
      get_scale_as_aniso_u=get_scale_as_aniso_u,
      max_possible_cc=max_possible_cc,
      **input_info())
  target_scale_factors = info.target_scale_factors

  if direction_vector:
    print ("\n Analysis for direction vector (%5.2f, %5.2f, %5.2f): "% (
      direction_vector), file = out)

  if info.effective_b:
    print("\nEffective B value for CC*: %.3f A**2 " %(
        info.effective_b),file=out)

  if fraction_complete < min_fraction_complete:
    print("\nFraction complete (%5.2f) is less than minimum (%5.2f)..." %(
      fraction_complete,min_fraction_complete) + "\nSkipping scaling", file=out)
    target_scale_factors=flex.double(target_scale_factors.size()*(1.0,))
  print ("\nAverage CC: %.3f" %(cc_list.min_max_mean().mean),file=out)
  print("\nScale factors vs resolution:", file=out)
  print("Note 1: CC* estimated from sqrt(2*CC/(1+CC))", file=out)
  print("Note 2: CC estimated by fitting (smoothing) for values < %s" %(cc_cut), file=out)
  print("Note 3: Scale = A  CC*  rmsFc/rmsFo (A is normalization)", file=out)
  print("  d_min     rmsFo       rmsFc    CC      %s  Scale " %(
      text), file=out)

  for sthol2,scale,rms_fo,cc,rms_fc,orig_cc in zip(
     input_info.target_sthol2,target_scale_factors,rms_fo_list,
      cc_list,rms_fc_list,
      original_cc_list):
     print("%7.2f  %9.1f  %9.1f %7.3f  %7.3f  %5.2f " %(
       0.5/sthol2**0.5,rms_fo,rms_fc,orig_cc,cc,scale),
        file=out)

  si.target_scale_factors=target_scale_factors
  si.target_sthol2=input_info.target_sthol2
  si.d_min_list=input_info.d_min_list
  si.cc_list=cc_list
  si.rms_fo_list = rms_fo_list
  si.low_res_cc = cc_list[:low_res_bins].min_max_mean().mean # low-res average
  si.effective_b = info.effective_b
  si.effective_b_f_obs = info.effective_b_f_obs
  si.b_zero = info.b_zero
  si.rms = info.rms
  si.expected_rms_fc_list = expected_rms_fc_list

  return si

def get_sel_para(f_array, direction_vector, minimum_dot = 0.70):
    # get selections based on |dot(normalized_indices, direction_vector)|
    u = f_array.unit_cell()
    rcvs = u.reciprocal_space_vector(f_array.indices())
    norms = rcvs.norms()
    norms.set_selected((norms == 0),1)
    index_directions = rcvs/norms
    sel = (flex.abs(index_directions.dot(direction_vector)) > minimum_dot)
    return sel

def get_normalized_weights_para(f_array,direction_vectors, dv,
    include_all_in_lowest_bin = None):

    sum_weights = flex.double(f_array.size(),0)
    current_weights = None
    for direction_vector in direction_vectors:
      weights = get_weights_para(f_array, direction_vector,
        include_all_in_lowest_bin = include_all_in_lowest_bin)
      if direction_vector == dv:
        current_weights = weights
      sum_weights += weights
    sum_weights.set_selected((sum_weights <= 1.e-10), 1.e-10)
    return current_weights * (1/sum_weights)

def get_weights_para(f_array, direction_vector,
       weight_by_cos = True,
       min_dot = 0.7,
       very_high_dot = 0.9,
       pre_factor_scale= 10,
       include_all_in_lowest_bin = None):
    u = f_array.unit_cell()
    rcvs = u.reciprocal_space_vector(f_array.indices())
    norms = rcvs.norms()
    norms.set_selected((norms == 0),1)
    index_directions = rcvs/norms
    if weight_by_cos:

      weights = flex.abs(index_directions.dot(direction_vector))
      sel = (weights < min_dot)
      weights.set_selected(sel,0)

      weights += (1-very_high_dot)  # move very_high to 1.0
      sel = (weights > 1)
      weights.set_selected(sel,1) # now from (min_dot+(1-very_high_dot) to 1)

      weights = (weights - 1 ) * pre_factor_scale
      sel = (weights > -20)  &  (weights < 20)
      weights.set_selected(sel, flex.exp(weights.select(sel)))
      weights.set_selected(~sel,0)
 

    else:
      weights = flex.double(index_directions.size(),0)
      sel = (flex.abs(index_directions.dot(direction_vector)) > min_dot)
      weights.set_selected(sel,1)
    if include_all_in_lowest_bin:
      i_bin = 1
      sel       = f_array.binner().selection(i_bin)
      weights.set_selected(sel, 1.0)  # full weights on low-res in all directions
    return weights

def get_nearest_lattice_points(unit_cell, reciprocal_space_vectors):
  lattice_points=flex.vec3_double()
  v = matrix.sqr(unit_cell.fractionalization_matrix()).inverse()
  for x in reciprocal_space_vectors:
    lattice_points.append(v*x)
  lattice_points=lattice_points.iround()
  return lattice_points

def get_target_scale_factors(
     f_array = None,
     ratio_list = None,
     rms_fo_list = None,
     cc_list = None,
     n_list = None,
     target_sthol2 = None,
     d_min_list = None,
     max_possible_cc = None,
     pseudo_likelihood = None,
     equalize_power = None,
     is_model_based = None,
     skip_scale_factor = None,
     maximum_scale_factor = None,
     b_eff = None,
     get_scale_as_aniso_u=None,
     out = sys.stdout):


  weighted_cc = 0
  weighted = 0

  target_scale_factors=flex.double()
  sum_w=0.
  sum_w_scale=0.
  for i_bin in f_array.binner().range_used():
    index=i_bin-1
    ratio=ratio_list[index]
    cc=cc_list[index]
    sthol2=target_sthol2[index]
    d_min=d_min_list[index]


    corrected_cc=max(0.00001,min(1.,cc/max(1.e-10,max_possible_cc)))

    if (not is_model_based): # cc is already cc*
      scale_on_fo=ratio * corrected_cc
    elif b_eff is not None:
      if pseudo_likelihood:
        scale_on_fo=(cc/max(0.001,1-cc**2))
      else: # usual
        scale_on_fo=ratio * min(1.,
          max(0.00001,corrected_cc) * math.exp(min(20.,sthol2*b_eff)) )
    else:
      scale_on_fo=ratio * min(1.,max(0.00001,corrected_cc))

    w = n_list[index]*(rms_fo_list[index])**2
    sum_w += w
    sum_w_scale += w * scale_on_fo**2
    target_scale_factors.append(scale_on_fo)
    weighted_cc += n_list[index]*rms_fo_list[index] * scale_on_fo * corrected_cc
    weighted += n_list[index]*rms_fo_list[index] * scale_on_fo

  weighted_cc = weighted_cc/max(1.e-10,weighted)

  if not pseudo_likelihood and not skip_scale_factor: # normalize
    avg_scale_on_fo = (sum_w_scale/max(1.e-10,sum_w))**0.5
    if equalize_power and avg_scale_on_fo>1.e-10:
      # XXX do not do this if only 1 bin has values > 0
      scale_factor = 1/avg_scale_on_fo
    else: # usual
      scale_factor=1./target_scale_factors.min_max_mean().max
    target_scale_factors=\
      target_scale_factors*scale_factor
  if maximum_scale_factor and \
     target_scale_factors.min_max_mean().max > maximum_scale_factor:
    truncated_scale_factors = flex.double()
    for x in target_scale_factors:
      truncated_scale_factors.append(min(maximum_scale_factor,x ))
    target_scale_factors = truncated_scale_factors

  if get_scale_as_aniso_u:
    # Get effective B for cc_list and target_sthol2
    info = get_effective_b(values = cc_list,
      sthol2_values = target_sthol2)
    effective_b = info.effective_b
    b_zero= info.b_zero
    rms= info.rms

    # Also get effective_b for amplitudes
    amplitude_info = get_effective_b(values = rms_fo_list/max(
       1.e-10,rms_fo_list[0]),
      sthol2_values = target_sthol2)
    effective_b_f_obs = amplitude_info.effective_b

  else:
    effective_b = None
    effective_b_f_obs = None
    b_zero= None
    rms = None
  return group_args(
    target_scale_factors = target_scale_factors,
    weighted_cc = weighted_cc,
    effective_b = effective_b,
    effective_b_f_obs = effective_b_f_obs,
    b_zero = b_zero,
    rms = rms
  )

def get_effective_b(values = None,
      sthol2_values = None,
       max_tries_per_iter = 10,
       max_iter = 10,
       tol = 1.e-6,
       effective_b = None,
       b_zero = None,
       delta_b = 50):
  if effective_b is not None and b_zero is not None:
      # calculate update
      best_info = None
      for i in range(-max_tries_per_iter//2,max_tries_per_iter//2):
        b_value = effective_b + i* delta_b
        info=get_b_calc(b_value, sthol2_values, values)
        if not best_info or info.rms  < best_info.rms:
          best_info = info
          best_info.effective_b = b_value
      effective_b = best_info.effective_b
      rms = best_info.rms
      b_zero = best_info.b_zero

  else:
     effective_b = 0
     b_zero = 1
     finished = False
     best_info = None
     for iter in range(max_iter):
       info = get_effective_b(values = values,
         sthol2_values = sthol2_values,
         max_tries_per_iter = max_tries_per_iter,
         effective_b = effective_b,
         b_zero =  b_zero,
         delta_b = delta_b)
       effective_b = info.effective_b
       b_zero = info.b_zero
       rms = info.rms
       best_info = info
       if finished:
         break
       else:
         delta_b = delta_b * 0.75

  return group_args(
    effective_b = effective_b,
    b_zero = b_zero,
    rms = rms,
    values = best_info.values,
    calc_values=best_info.calc_values)

def get_b_calc( b_value, sthol2_values, values):
  import math
  sum= 0.
  sumx= 0.
  sumy= 0.
  sum2= 0.
  sumn=0.
  calc_values = flex.double()
  for sthol2, value in zip (sthol2_values, values):
    calc_values.append(math.exp(max(-20.,min(20.,
      - b_value* sthol2))))
  #b_zero = values.min_max_mean().mean/calc_values.min_max_mean().mean
  b_zero = values[0]/calc_values[0]
  calc_values *= b_zero
  from libtbx.test_utils import approx_equal
  assert approx_equal(values[0],calc_values[0])
  rms = ((flex.pow2(values-calc_values)).min_max_mean().mean)**0.5
  return group_args(
    b_zero=b_zero,
    values=values,
    calc_values=calc_values,
    rms=rms)


def analyze_aniso(f_array=None,map_coeffs=None,b_iso=None,resolution=None,
     get_remove_aniso_object=True,
     invert = False,
     remove_aniso=None, aniso_obj=None, out=sys.stdout):
  # optionally remove anisotropy and set all directions to mean value
  #  return array and analyze_aniso_object
  #  resolution can be None, b_iso can be None
  #  if remove_aniso is None, just analyze and return original array

  if map_coeffs:  # convert to f and apply
    from cctbx.maptbx.segment_and_split_map import map_coeffs_as_fp_phi
    f_local,phases_local=map_coeffs_as_fp_phi(map_coeffs)
    f_local,f_local_aa=analyze_aniso(f_array=f_local,
       aniso_obj=aniso_obj,
       get_remove_aniso_object=get_remove_aniso_object,
       remove_aniso=remove_aniso, resolution=resolution,out=out)
    return f_local.phase_transfer(phase_source=phases_local,deg=True),f_local_aa

  elif not get_remove_aniso_object:
    return f_array,aniso_obj # don't do anything

  else:  # have f_array and resolution
    if not aniso_obj:
      aniso_obj=analyze_aniso_object()
      aniso_obj.set_up_aniso_correction(f_array=f_array,d_min=resolution,
        b_iso=b_iso, invert = invert)

    if remove_aniso and aniso_obj and aniso_obj.b_cart:
      f_array=aniso_obj.apply_aniso_correction(f_array=f_array)
      print("Removing anisotropy with b_cart=(%7.2f,%7.2f,%7.2f)\n" %(
        aniso_obj.b_cart[:3]), file=out)
    return f_array,aniso_obj

def scale_amplitudes(model_map_coeffs=None,
    map_coeffs=None,
    external_map_coeffs=None,
    first_half_map_coeffs=None,
    second_half_map_coeffs=None,
    si=None,resolution=None,overall_b=None,
    fraction_complete=None,
    min_fraction_complete=0.05,
    map_calculation=True,
    verbose=False,
    out=sys.stdout):
  # Figure out resolution_dependent sharpening to optimally
  #  match map and model. Then apply it as usual.
  #  if second_half_map_coeffs instead of model,
  #     use second_half_map_coeffs same as
  #    normalized model map_coeffs, except that the target fall-off should be
  #    skipped (could use fall-off based on a dummy model...)

  if model_map_coeffs and (
      not first_half_map_coeffs or not second_half_map_coeffs):
    is_model_based=True
  elif si.target_scale_factors or (
       first_half_map_coeffs and second_half_map_coeffs) or (
        external_map_coeffs):
    is_model_based=False
  else:
    assert map_coeffs
    if si.is_model_sharpening():
      is_model_based=True
    else:
      is_model_based=False

  if si.verbose and not verbose:
    verbose=True

  # if si.target_scale_factors is set, just use those scale factors

  from cctbx.maptbx.segment_and_split_map import map_coeffs_as_fp_phi,get_b_iso

  f_array,phases=map_coeffs_as_fp_phi(map_coeffs)

  (d_max,d_min)=f_array.d_max_min(d_max_is_highest_defined_if_infinite=True)
  if not f_array.binner():
    f_array.setup_binner(n_bins=si.n_bins,d_max=d_max,d_min=d_min)
    f_array.binner().require_all_bins_have_data(min_counts=1,
      error_string="Please use a lower value of n_bins")

  if resolution is None:
    resolution=si.resolution
  if resolution is None:
    raise Sorry("Need resolution for model sharpening")

  obs_b_iso=get_b_iso(f_array,d_min=resolution)
  print("\nEffective b_iso of observed data: %6.1f A**2" %(obs_b_iso), file=out)

  if not si.target_scale_factors: # get scale factors if don't already have them
    si=calculate_fsc(si=si,
      f_array=f_array,  # just used for binner
      map_coeffs=map_coeffs,
      model_map_coeffs=model_map_coeffs,
      first_half_map_coeffs=first_half_map_coeffs,
      second_half_map_coeffs=second_half_map_coeffs,
      external_map_coeffs=external_map_coeffs,
      resolution=resolution,
      fraction_complete=fraction_complete,
      min_fraction_complete=min_fraction_complete,
      is_model_based=is_model_based,
      cc_cut=si.cc_cut,
      scale_using_last=si.scale_using_last,
      max_cc_for_rescale=si.max_cc_for_rescale,
      pseudo_likelihood=si.pseudo_likelihood,
      verbose=verbose,
      out=out)
    # now si.target_scale_factors array are the scale factors

  # Now create resolution-dependent coefficients from the scale factors

  if not si.target_scale_factors: # nothing to do
    print("\nNo scaling applied", file=out)
    map_data=calculate_map(map_coeffs=map_coeffs,n_real=si.n_real)
    return map_and_b_object(map_data=map_data)
  elif not map_calculation:
    return map_and_b_object()
  else:  # apply scaling
    if si.pseudo_likelihood:
      print("Normalizing structure factors", file=out)
      f_array=quasi_normalize_structure_factors(f_array,set_to_minimum=0.01,
        pseudo_likelihood=si.pseudo_likelihood)
      f_array.setup_binner(n_bins=si.n_bins,d_max=d_max,d_min=d_min)
    map_and_b=apply_target_scale_factors(
      f_array=f_array,phases=phases,resolution=resolution,
      target_scale_factors=si.target_scale_factors,
      n_real=si.n_real,
      out=out)
    return map_and_b

def apply_target_scale_factors(f_array=None,phases=None,
   resolution=None,target_scale_factors=None,
   n_real=None,
   return_map_coeffs=None,out=sys.stdout):
    from cctbx.maptbx.segment_and_split_map import get_b_iso
    f_array_b_iso=get_b_iso(f_array,d_min=resolution)
    scale_array=f_array.binner().interpolate(
      target_scale_factors, 1) # d_star_power=1
    scaled_f_array=f_array.customized_copy(data=f_array.data()*scale_array)
    scaled_f_array_b_iso=get_b_iso(scaled_f_array,d_min=resolution)
    print("\nInitial b_iso for "+\
      "map: %5.1f A**2     After applying scaling: %5.1f A**2" %(
      f_array_b_iso,scaled_f_array_b_iso), file=out)
    new_map_coeffs=scaled_f_array.phase_transfer(phase_source=phases,deg=True)
    assert new_map_coeffs.size() == f_array.size()
    if return_map_coeffs:
      return new_map_coeffs

    map_data=calculate_map(map_coeffs=new_map_coeffs,n_real=n_real)
    return map_and_b_object(map_data=map_data,starting_b_iso=f_array_b_iso,
      final_b_iso=scaled_f_array_b_iso)
def calculate_map(map_coeffs=None,crystal_symmetry=None,n_real=None):

  if crystal_symmetry is None: crystal_symmetry=map_coeffs.crystal_symmetry()
  from cctbx.development.create_models_or_maps import get_map_from_map_coeffs
  map_data=get_map_from_map_coeffs(
     map_coeffs=map_coeffs,crystal_symmetry=crystal_symmetry, n_real=n_real)
  return map_data

def get_sharpened_map(ma=None,phases=None,b=None,resolution=None,
    n_real=None,d_min_ratio=None):
  assert n_real is not None
  sharpened_ma=adjust_amplitudes_linear(ma,b[0],b[1],b[2],resolution=resolution,
     d_min_ratio=d_min_ratio)
  new_map_coeffs=sharpened_ma.phase_transfer(phase_source=phases,deg=True)
  map_data=calculate_map(map_coeffs=new_map_coeffs,n_real=n_real)
  return map_data

def calculate_match(target_sthol2=None,target_scale_factors=None,b=None,resolution=None,d_min_ratio=None,rmsd=None,fraction_complete=None):

  if fraction_complete is None:
    pass # XXX not implemented for fraction_complete

  if rmsd is None:
    rmsd=resolution/3.
    print("Setting rmsd to %5.1f A based on resolution of %5.1f A" %(
       rmsd,resolution), file=out)

  if rmsd is None:
    b_eff=None
  else:
    b_eff=8*3.14159*rmsd**2

  d_min=d_min_ratio*resolution
  sthol2_2=0.25/resolution**2
  sthol2_1=sthol2_2*0.5
  sthol2_3=0.25/d_min**2
  b0=0.0
  b1=b[0]
  b2=b[1]
  b3=b[2]
  b3_use=b3+b2

  resid=0.
  import math
  value_list=flex.double()
  scale_factor_list=flex.double()

  for sthol2,scale_factor in zip(target_sthol2,target_scale_factors):
    if sthol2 > sthol2_2:
      value=b2+(sthol2-sthol2_2)*(b3_use-b2)/(sthol2_3-sthol2_2)
    elif sthol2 > sthol2_1:
      value=b1+(sthol2-sthol2_1)*(b2-b1)/(sthol2_2-sthol2_1)
    else:
      value=b0+(sthol2-0.)*(b1-b0)/(sthol2_1-0.)

    value=math.exp(value)
    if b_eff is not None:
      value=value*math.exp(-sthol2*b_eff)
    value_list.append(value)
    scale_factor_list.append(scale_factor)
  mean_value=value_list.min_max_mean().mean
  mean_scale_factor=scale_factor_list.min_max_mean().mean
  ratio=mean_scale_factor/mean_value
  value_list=value_list*ratio
  delta_list=value_list-scale_factor_list
  delta_sq_list=delta_list*delta_list
  resid=delta_sq_list.min_max_mean().mean
  return resid

def calculate_adjusted_sa(ma,phases,b,
    resolution=None,
    d_min_ratio=None,
    solvent_fraction=None,
    region_weight=None,
    max_regions_to_test=None,
    sa_percent=None,
    fraction_occupied=None,
    wrapping=None,
    n_real=None):

  map_data=get_sharpened_map(ma,phases,b,resolution,n_real=n_real,
    d_min_ratio=d_min_ratio)
  from cctbx.maptbx.segment_and_split_map import score_map

  si=score_map(
    map_data=map_data,
    solvent_fraction=solvent_fraction,
    fraction_occupied=fraction_occupied,
    wrapping=wrapping,
    sa_percent=sa_percent,
    region_weight=region_weight,
    max_regions_to_test=max_regions_to_test,
    out=null_out())
  return si.adjusted_sa

def get_kurtosis(data=None):
  mean=data.min_max_mean().mean
  sd=data.standard_deviation_of_the_sample()
  x=data-mean
  return (x**4).min_max_mean().mean/sd**4

class analyze_aniso_object:
  def __init__(self):

    self.b_cart=None
    self.b_cart_aniso_removed=None

  def set_up_aniso_correction(self,f_array=None,b_iso=None,d_min=None,
     b_cart_to_remove = None, invert = False):

    assert f_array is not None
    if not d_min:
      (d_max,d_min)=f_array.d_max_min(d_max_is_highest_defined_if_infinite=True)

    if b_cart_to_remove and b_iso:
      self.b_cart=b_cart_to_remove
      self.b_cart_aniso_removed = [ -b_iso, -b_iso, -b_iso, 0, 0, 0] # change
    else:
      from cctbx.maptbx.segment_and_split_map import get_b_iso
      b_mean,aniso_scale_and_b=get_b_iso(f_array,d_min=d_min,
        return_aniso_scale_and_b=True)
      if not aniso_scale_and_b or not aniso_scale_and_b.b_cart:
        return # failed

      if b_iso is None:
        b_iso=b_mean  # use mean
      self.b_iso=b_iso

      self.b_cart=aniso_scale_and_b.b_cart  # current
      self.b_cart_aniso_removed = [ -b_iso, -b_iso, -b_iso, 0, 0, 0] # change
      if invert:
        self.b_cart = tuple([-x for x in self.b_cart])

      # ready to apply

  def apply_aniso_correction(self,f_array=None):

    if self.b_cart is None or self.b_cart_aniso_removed is None:
      return f_array  # nothing to do

    from mmtbx.scaling import absolute_scaling
    from cctbx import adptbx

    u_star= adptbx.u_cart_as_u_star(
      f_array.unit_cell(), adptbx.b_as_u( self.b_cart) )

    u_star_aniso_removed = adptbx.u_cart_as_u_star(
      f_array.unit_cell(), adptbx.b_as_u( self.b_cart_aniso_removed  ) )

    no_aniso_array = absolute_scaling.anisotropic_correction(
      f_array,0.0, u_star ,must_be_greater_than=-0.0001)

    no_aniso_array = absolute_scaling.anisotropic_correction(
      no_aniso_array,0.0,u_star_aniso_removed,must_be_greater_than=-0.0001)

    no_aniso_array=no_aniso_array.set_observation_type( f_array)
    return no_aniso_array


class refinery:
  def __init__(self,ma,phases,b,resolution,
    residual_target=None,
    solvent_fraction=None,
    region_weight=None,
    max_regions_to_test=None,
    sa_percent=None,
    fraction_occupied=None,
    wrapping=None,
    eps=0.01,
    tol=0.01,
    max_iterations=20,
    n_real=None,
    target_sthol2=None,
    target_scale_factors=None,
    d_min_ratio=None,
    rmsd=None,
    fraction_complete=None,
    dummy_run=False):

    self.ma=ma
    self.n_real=n_real
    self.phases=phases
    self.resolution=resolution
    self.d_min_ratio=d_min_ratio
    self.rmsd=rmsd
    self.fraction_complete=fraction_complete

    self.target_sthol2=target_sthol2
    self.target_scale_factors=target_scale_factors

    self.tol=tol
    self.eps=eps
    self.max_iterations=max_iterations

    self.solvent_fraction=solvent_fraction
    self.region_weight=region_weight
    self.max_regions_to_test=max_regions_to_test
    self.residual_target=residual_target
    self.sa_percent=sa_percent
    self.fraction_occupied=fraction_occupied
    self.wrapping=wrapping

    self.x = flex.double(b)

  def run(self):

    scitbx.lbfgs.run(target_evaluator=self,
      termination_params=scitbx.lbfgs.termination_parameters(
        traditional_convergence_test_eps=self.tol,
                     max_iterations=self.max_iterations,
       ))

  def show_result(self,out=sys.stdout):

    b=self.get_b()
    value = -1.*self.residual(b)
    print("Result: b1 %7.2f b2 %7.2f b3 %7.2f resolution %7.2f %s: %7.3f" %(
     b[0],b[1],b[2],self.resolution,self.residual_target,value), file=out)

    if self.ma:
      self.sharpened_ma=adjust_amplitudes_linear(
         self.ma,b[0],b[1],b[2],resolution=self.resolution,
         d_min_ratio=self.d_min_ratio)
    else:
      self.sharpened_ma=None
    return value

  def compute_functional_and_gradients(self):
    b = self.get_b()
    f = self.residual(b)
    g = self.gradients(b)
    return f, g

  def residual(self,b,restraint_weight=100.):

    if self.residual_target=='kurtosis':
      resid=-1.*calculate_kurtosis(self.ma,self.phases,b,self.resolution,
         n_real=self.n_real,d_min_ratio=self.d_min_ratio)

    elif self.residual_target=='adjusted_sa':
      resid=-1.*calculate_adjusted_sa(self.ma,self.phases,b,
        resolution=self.resolution,
        d_min_ratio=self.d_min_ratio,
        solvent_fraction=self.solvent_fraction,
        region_weight=self.region_weight,
        max_regions_to_test=self.max_regions_to_test,
        sa_percent=self.sa_percent,
        fraction_occupied=self.fraction_occupied,
        wrapping=self.wrapping,n_real=self.n_real)

    elif self.residual_target=='model':
      resid=calculate_match(target_sthol2=self.target_sthol2,
        target_scale_factors=self.target_scale_factors,
        b=b,
        resolution=self.resolution,
        d_min_ratio=self.d_min_ratio,
        emsd=self.rmsd,
        fraction_complete=self.complete)

    else:
      raise Sorry("residual_target must be kurtosis or adjusted_sa or match_target")

    # put in restraint so b[1] is not bigger than b[0]
    if b[1]>b[0]:  resid+=(b[1]-b[0])*restraint_weight
    # put in restraint so b[2] <=0
    if b[2]>0:  resid+=b[2]*restraint_weight
    return resid

  def gradients(self,b):

    result = flex.double()
    for i in range(len(list(b))):
      rs = []
      for signed_eps in [self.eps, -self.eps]:
        params_eps = deepcopy(b)
        params_eps[i] += signed_eps
        rs.append(self.residual(params_eps))
      result.append((rs[0]-rs[1])/(2*self.eps))
    return result

  def get_b(self):
    return list(self.x)

  def callback_after_step(self, minimizer):
    pass # can do anything here

def calculate_kurtosis(ma,phases,b,resolution,n_real=None,
    d_min_ratio=None):
  map_data=get_sharpened_map(ma,phases,b,resolution,n_real=n_real,
  d_min_ratio=d_min_ratio)
  return get_kurtosis(map_data.as_1d())

def run(map_coeffs=None,
  b=[0,0,0],
  sharpening_info_obj=None,
  resolution=None,
  residual_target=None,
  solvent_fraction=None,
  region_weight=None,
  max_regions_to_test=None,
  sa_percent=None,
  fraction_occupied=None,
  n_bins=None,
  eps=None,
  wrapping=False,
  n_real=False,
  target_sthol2=None,
  target_scale_factors=None,
  d_min_ratio=None,
  rmsd=None,
  fraction_complete=None,
  normalize_amplitudes_in_resdep=None,
  out=sys.stdout):

  if sharpening_info_obj:
    solvent_fraction=sharpening_info_obj.solvent_fraction
    wrapping=sharpening_info_obj.wrapping
    n_real=sharpening_info_obj.n_real
    fraction_occupied=sharpening_info_obj.fraction_occupied
    sa_percent=sharpening_info_obj.sa_percent
    region_weight=sharpening_info_obj.region_weight
    max_regions_to_test=sharpening_info_obj.max_regions_to_test
    residual_target=sharpening_info_obj.residual_target
    resolution=sharpening_info_obj.resolution
    d_min_ratio=sharpening_info_obj.d_min_ratio
    rmsd=sharpening_info_obj.rmsd
    fraction_complete=sharpening_info_obj.fraction_complete
    eps=sharpening_info_obj.eps
    n_bins=sharpening_info_obj.n_bins
    normalize_amplitudes_in_resdep= \
    sharpening_info_obj.normalize_amplitudes_in_resdep
  else:
    from cctbx.maptbx.segment_and_split_map import sharpening_info
    sharpening_info_obj=sharpening_info()


  if map_coeffs:
    phases=map_coeffs.phases(deg=True)
    ma=map_coeffs.as_amplitude_array()
  else:
    phases=None
    ma=None

  # set some defaults
  if residual_target is None: residual_target='kurtosis'

  assert (solvent_fraction is not None ) or residual_target=='kurtosis'
  assert resolution is not None

  if residual_target=='adjusted_sa' and solvent_fraction is None:
    raise Sorry("Solvent fraction is required for residual_target=adjusted_sa")

  if eps is None and residual_target=='kurtosis':
    eps=0.01
  elif eps is None:
    eps=0.5

  if fraction_complete is None:
    pass # XXX not implemented

  if rmsd is None:
    rmsd=resolution/3.
    print("Setting rmsd to %5.1f A based on resolution of %5.1f A" %(
       rmsd,resolution), file=out)

  if fraction_occupied is None: fraction_occupied=0.20
  if region_weight is None: region_weight=20.
  if sa_percent is None: sa_percent=30.
  if n_bins is None: n_bins=20
  if max_regions_to_test is None: max_regions_to_test=30


  # Get initial value

  best_b=b
  print("Getting starting value ...",residual_target, file=out)
  refined = refinery(ma,phases,b,resolution,
    residual_target=residual_target,
    solvent_fraction=solvent_fraction,
    region_weight=region_weight,
    sa_percent=sa_percent,
    max_regions_to_test=max_regions_to_test,
    fraction_occupied=fraction_occupied,
    wrapping=wrapping,
    n_real=n_real,
    target_sthol2=target_sthol2,
    target_scale_factors=target_scale_factors,
    d_min_ratio=d_min_ratio,
    rmsd=rmsd,
    fraction_complete=fraction_complete,
    eps=eps)


  starting_result=refined.show_result(out=out)
  print("Starting value: %7.2f" %(starting_result), file=out)

  if ma:
    (d_max,d_min)=ma.d_max_min(d_max_is_highest_defined_if_infinite=True)
    ma.setup_binner(n_bins=n_bins,d_max=d_max,d_min=d_min)
    if normalize_amplitudes_in_resdep:
      print("Normalizing structure factors...", file=out)
      ma=quasi_normalize_structure_factors(ma,set_to_minimum=0.01)
  else:
    assert resolution is not None

  refined = refinery(ma,phases,b,resolution,
    residual_target=residual_target,
    solvent_fraction=solvent_fraction,
    region_weight=region_weight,
    max_regions_to_test=max_regions_to_test,
    sa_percent=sa_percent,
    fraction_occupied=fraction_occupied,
    wrapping=wrapping,
    n_real=n_real,
    target_sthol2=target_sthol2,
    target_scale_factors=target_scale_factors,
    d_min_ratio=d_min_ratio,
    rmsd=rmsd,
    fraction_complete=fraction_complete,
    eps=eps)

  starting_normalized_result=refined.show_result(out=out)
  print("Starting value after normalization: %7.2f" %(
     starting_normalized_result), file=out)
  best_sharpened_ma=ma
  best_result=starting_normalized_result
  best_b=refined.get_b()

  refined.run()

  final_result=refined.show_result(out=out)
  print("Final value: %7.2f" %(
     final_result), file=out)

  if final_result>best_result:
    best_sharpened_ma=refined.sharpened_ma
    best_result=final_result
    best_b=refined.get_b()
  print("Best overall result: %7.2f: " %(best_result), file=out)

  sharpening_info_obj.resolution_dependent_b=best_b
  return best_sharpened_ma,phases


if (__name__ == "__main__"):
  args=sys.argv[1:]
  residual_target='kurtosis'
  if 'adjusted_sa' in args:
    residual_target='adjusted_sa'
  resolution=2.9 # need to set this as nominal resolution
  # get data
  map_coeffs=get_amplitudes(args)

  new_map_coeffs=run(map_coeffs=map_coeffs,
    resolution=resolution,
    residual_target=residual_target)
  mtz_dataset=new_map_coeffs.as_mtz_dataset(column_root_label="FWT")
  mtz_dataset.mtz_object().write(file_name='sharpened.mtz')
