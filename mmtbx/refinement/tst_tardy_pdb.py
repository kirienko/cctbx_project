from __future__ import division
import mmtbx.refinement.tardy
from mmtbx.monomer_library import pdb_interpretation
import mmtbx.monomer_library.server as mon_lib_server
import iotbx.pdb
import iotbx.phil
import cctbx.geometry_restraints
from cctbx import maptbx
from cctbx.array_family import flex
from scitbx.rigid_body.essence import tst_molecules
import scitbx.graph.tardy_tree
from scitbx import matrix
import libtbx.phil.command_line
from libtbx.utils import Sorry, format_cpu_times
from libtbx.str_utils import format_value
from libtbx import Auto, group_args
import random
import sys, os

class potential_object(object):

  def __init__(O,
        density_map,
        geo_manager,
        reduced_geo_manager,
        nonbonded_attenuation_factor,
        real_space_gradients_delta,
        real_space_target_weight,
        ideal_sites_cart):
    O.density_map = density_map
    O.geo_manager = geo_manager
    O.reduced_geo_manager = reduced_geo_manager
    assert isinstance(
      geo_manager.nonbonded_function,
      cctbx.geometry_restraints.prolsq_repulsion_function)
    assert nonbonded_attenuation_factor > 0
    assert nonbonded_attenuation_factor <= 1
    O.custom_nonbonded_function = geo_manager.nonbonded_function \
      .customized_copy(k_rep=nonbonded_attenuation_factor)
    O.real_space_gradients_delta = real_space_gradients_delta
    O.real_space_target_weight = real_space_target_weight
    O.ideal_sites_cart = ideal_sites_cart
    #
    O.last_sites_moved = None
    O.f = None
    O.g = None
    O.last_grms = None

  def e_pot(O, sites_moved):
    if (O.last_sites_moved is not sites_moved):
      O.last_sites_moved = sites_moved
      sites_cart = flex.vec3_double(sites_moved)
      #
      if (O.reduced_geo_manager is None):
        flags = None
      else:
        flags = cctbx.geometry_restraints.flags.flags(nonbonded=True)
      geo_energies = O.geo_manager.energies_sites(
        sites_cart=sites_cart,
        flags=flags,
        custom_nonbonded_function=O.custom_nonbonded_function,
        compute_gradients=True)
      O.f = geo_energies.target
      O.g = geo_energies.gradients
      if (O.reduced_geo_manager is not None):
        reduced_geo_energies = O.reduced_geo_manager.energies_sites(
          sites_cart=sites_cart,
          compute_gradients=True)
        O.f += reduced_geo_energies.target
        O.g += reduced_geo_energies.gradients
      O.last_grms = group_args(geo=flex.mean_sq(O.g.as_double())**0.5)
      #
      if (O.density_map is not None):
        rs_f = maptbx.real_space_target_simple(
          unit_cell=O.geo_manager.crystal_symmetry.unit_cell(),
          density_map=O.density_map,
          sites_cart=sites_cart)
        rs_g = maptbx.real_space_gradients_simple(
          unit_cell=O.geo_manager.crystal_symmetry.unit_cell(),
          density_map=O.density_map,
          sites_cart=sites_cart,
          delta=O.real_space_gradients_delta)
        rs_f *= -O.real_space_target_weight
        rs_g *= -O.real_space_target_weight
        O.f += rs_f
        O.g += rs_g
        O.last_grms.real = flex.mean_sq(rs_g.as_double())**0.5
        O.last_grms.real_or_xray = "real"
      #
      O.last_grms.total = flex.mean_sq(O.g.as_double())**0.5
    return O.f

  def d_e_pot_d_sites(O, sites_moved):
    O.e_pot(sites_moved=sites_moved)
    return matrix.col_list(O.g)

def cartesian_random_displacements(sites_cart, target_rmsd, max_trials=10):
  assert sites_cart.size() != 0
  for i in xrange(max_trials):
    shifts_cart = flex.vec3_double(flex.random_double(
      size=sites_cart.size()*3, factor=2) - 1)
    rmsd = (flex.sum(shifts_cart.dot()) / sites_cart.size()) ** 0.5
    if (rmsd > 1.e-6): break # to avoid numerical problems
  else:
    raise RuntimeError
  shifts_cart *= (target_rmsd / rmsd)
  return sites_cart + shifts_cart

def run_test(params, pdb_files, other_files, callback=None, log=None):
  if (log is None): log = sys.stdout
  if (params.random_seed is not None):
    random.seed(params.random_seed)
    flex.set_random_seed(value=params.random_seed)
  #
  if (len(pdb_files) != 0):
    print >> log, "PDB files:"
    for file_name in pdb_files:
      print >> log, " ", file_name
    print >> log
  if (len(other_files) != 0):
    print >> log, "Other files:"
    for file_name in other_files:
      print >> log, " ", file_name
    print >> log
  #
  assert len(pdb_files) in [1, 2]
  #
  pdb_interpretation_params = pdb_interpretation.master_params.extract()
  pdb_interpretation_params.dihedral_function_type \
    = params.dihedral_function_type
  processed_pdb_files = pdb_interpretation.run(
    args=pdb_files[-1:]+other_files,
    params=pdb_interpretation_params,
    strict_conflict_handling=False,
    substitute_non_crystallographic_unit_cell_if_necessary=True,
    return_all_processed_pdb_files=True,
    log=log)
  assert len(processed_pdb_files) == 1
  print >> log
  #
  xs = processed_pdb_files[0].xray_structure()
  geo_manager = processed_pdb_files[0].geometry_restraints_manager()
  labels = [sc.label for sc in xs.scatterers()]
  ideal_sites_cart = xs.sites_cart()
  sites = matrix.col_list(ideal_sites_cart)
  masses = xs.atomic_weights()
  #
  if (params.tardy_displacements is not None):
    def get_sim_no_potential():
      tardy_tree = geo_manager.construct_tardy_tree(sites=sites)
      return tst_molecules.simulation(
        labels=labels,
        sites=sites,
        masses=masses,
        tardy_tree=tardy_tree,
        potential_obj=None)
    def get_sim_no_density():
      tardy_tree = scitbx.graph.tardy_tree.construct(sites=sites, edge_list=[])
      tardy_tree.finalize()
      potential_obj = potential_object(
        density_map=None,
        geo_manager=geo_manager,
        reduced_geo_manager=None,
        nonbonded_attenuation_factor=params.nonbonded_attenuation_factor,
        real_space_gradients_delta=None,
        real_space_target_weight=None,
        ideal_sites_cart=None)
      return tst_molecules.simulation(
        labels=labels,
        sites=sites,
        masses=masses,
        tardy_tree=tardy_tree,
        potential_obj=potential_obj)
    if (params.tardy_displacements is Auto):
      auto_params = params.tardy_displacements_auto
      target_rmsd = \
          params.structure_factors_high_resolution \
        * auto_params.rmsd_vs_high_resolution_factor
      target_rmsd_tol = \
          params.structure_factors_high_resolution \
        * auto_params.rmsd_tolerance
      assert target_rmsd > 0
      assert target_rmsd_tol > 0
      print >> log, "Random displacements (%s):" \
        % params.tardy_displacements_auto.parameterization
      print >> log, "  high resolution: %.6g" \
        % params.structure_factors_high_resolution
      print >> log, "  target rmsd: %.6g" % target_rmsd
      print >> log, "  target rmsd tolerance: %.6g" % target_rmsd_tol
      log.flush()
      def raise_max_steps_exceeded(var_name, rmsd_history):
        msg = [
          "tardy_displacements_auto.max_steps exceeded:",
          "  %        -13s  rmsd" % var_name]
        for var_rmsd in rmsd_history:
          msg.append("  %13.6e  %13.6e" % var_rmsd)
        raise Sorry("\n".join(msg))
      if (params.tardy_displacements_auto.parameterization == "cartesian"):
        multiplier = 1.5
        rmsd_history = []
        for i_step in xrange(auto_params.max_steps):
          sites = matrix.col_list(cartesian_random_displacements(
            sites_cart=ideal_sites_cart,
            target_rmsd=target_rmsd*multiplier))
          sim = get_sim_no_density()
          sim.minimization(max_iterations=20)
          sites = sim.sites_moved()
          sites_moved = flex.vec3_double(sites)
          rmsd = sites_moved.rms_difference(ideal_sites_cart)
          rmsd_history.append((multiplier, rmsd))
          print >> log, "    multiplier, rmsd: %13.6e, %13.6e" \
            % rmsd_history[-1]
          log.flush()
          if (rmsd < target_rmsd - target_rmsd_tol):
            if (rmsd != 0):
              multiplier = min(
                multiplier*2, max(
                  multiplier*1.2,
                    target_rmsd / rmsd))
            else:
              multiplier *= 2
          else:
            if (rmsd <= target_rmsd + target_rmsd_tol):
              break
            multiplier *= max(0.5, target_rmsd/rmsd)
        else:
          raise_max_steps_exceeded(
            var_name="multiplier", rmsd_history=rmsd_history)
        del rmsd_history
        print >> log, "  actual rmsd: %.6g" % rmsd
        print >> log
      elif (params.tardy_displacements_auto.parameterization == "constrained"):
        sim = get_sim_no_potential()
        sim.assign_random_velocities()
        delta_t = auto_params.first_delta_t
        rmsd_history = []
        assert auto_params.max_steps > 0
        for i_step in xrange(auto_params.max_steps):
          prev_q = sim.pack_q()
          prev_qd = sim.pack_qd()
          sim.dynamics_step(delta_t=delta_t)
          sites_moved = flex.vec3_double(sim.sites_moved())
          rmsd = sites_moved.rms_difference(ideal_sites_cart)
          rmsd_history.append((delta_t, rmsd))
          if (rmsd < target_rmsd - target_rmsd_tol):
            delta_t *= 2 - rmsd / target_rmsd
          else:
            if (rmsd <= target_rmsd + target_rmsd_tol):
              break
            sim.unpack_q(packed_q=prev_q)
            sim.unpack_qd(packed_qd=prev_qd)
            delta_t *= 0.5
          prev_q = None
          prev_qd = None
        else:
          raise_max_steps_exceeded(
            var_name="delta_t", rmsd_history=rmsd_history)
        del rmsd_history
        print >> log, "  actual rmsd: %.6g" % rmsd
        print >> log, "  tardy_displacements=%s" % ",".join(
          ["%.6g" % v for v in sim.pack_q()])
        print >> log
        sites = sim.sites_moved()
      else:
        raise AssertionError
    else:
      sim = get_sim_no_potential()
      q = sim.pack_q()
      if (len(params.tardy_displacements) != len(q)):
        print >> log, "tardy_displacements:", params.tardy_displacements
        hinge_edges = sim.tardy_tree.cluster_manager.hinge_edges
        assert len(hinge_edges) == len(sim.bodies)
        for (i,j),B in zip(hinge_edges, sim.bodies):
          if (i == -1): si = "root"
          else: si = sim.labels[i]
          sj = sim.labels[j]
          print >> log, "%21s - %-21s: %d dof, %d q_size" % (
            si, sj, B.J.degrees_of_freedom, B.J.q_size)
        print >> log, "Zero displacements:"
        print >> log, "  tardy_displacements=%s" % ",".join(
          [str(v) for v in q])
        raise Sorry("Incompatible tardy_displacements.")
      sim.unpack_q(packed_q=flex.double(params.tardy_displacements))
      sites = sim.sites_moved()
  #
  if (params.emulate_cartesian):
    tardy_tree = scitbx.graph.tardy_tree.construct(sites=sites, edge_list=[])
    tardy_tree.finalize()
  else:
    tardy_tree = geo_manager.construct_tardy_tree(sites=sites)
  print >> log, "tardy_tree summary:"
  tardy_tree.show_summary(vertex_labels=labels, out=log, prefix="  ")
  print >> log
  if (params.emulate_cartesian):
    reduced_geo_manager = None
  else:
    reduced_geo_manager = geo_manager.reduce_for_tardy(tardy_tree=tardy_tree)
  #
  if (len(pdb_files) == 2):
    ideal_pdb_inp = iotbx.pdb.input(file_name=pdb_files[0])
    ideal_pdb_hierarchy = ideal_pdb_inp.construct_hierarchy()
    assert ideal_pdb_hierarchy.is_similar_hierarchy(
      processed_pdb_files[0].all_chain_proxies.pdb_hierarchy)
    ideal_sites_cart = ideal_pdb_hierarchy.atoms().extract_xyz()
    xs.set_sites_cart(sites_cart=ideal_sites_cart)
  fft_map = xs.structure_factors(
    d_min=params.structure_factors_high_resolution).f_calc().fft_map()
  fft_map.apply_sigma_scaling()
  #
  real_space_gradients_delta = \
      params.structure_factors_high_resolution \
    * params.real_space_gradients_delta_resolution_factor
  potential_obj = potential_object(
    density_map=fft_map.real_map(),
    geo_manager=geo_manager,
    reduced_geo_manager=reduced_geo_manager,
    nonbonded_attenuation_factor=params.nonbonded_attenuation_factor,
    real_space_gradients_delta=real_space_gradients_delta,
    real_space_target_weight=params.real_space_target_weight,
    ideal_sites_cart=ideal_sites_cart)
  sim = tst_molecules.simulation(
    labels=labels,
    sites=sites,
    masses=masses,
    tardy_tree=tardy_tree,
    potential_obj=potential_obj)
  mmtbx.refinement.tardy.action(
    sim=sim,
    params=params,
    callback=callback,
    log=log)
  print >> log

def get_master_phil():
  return iotbx.phil.parse(
    input_string=mmtbx.refinement.tardy.master_phil_str + """\
structure_factors_high_resolution = 3
  .type = float
real_space_target_weight = 100
  .type = float
real_space_gradients_delta_resolution_factor = 1/3
  .type = float
emulate_cartesian = False
  .type = bool
random_seed = None
  .type = int
tardy_displacements = None
  .type = floats
tardy_displacements_auto {
  parameterization = *constrained cartesian
    .type = choice
    .optional = False
  rmsd_vs_high_resolution_factor = 1/3
    .type = float
  rmsd_tolerance = 0.1
    .type = float
  first_delta_t = 0.001
    .type = float
  max_steps = 100
    .type = int
}
%(dihedral_function_type_params_str)s
""" % pdb_interpretation.__dict__)

def run(args, callback=None):
  master_phil = get_master_phil()
  argument_interpreter = libtbx.phil.command_line.argument_interpreter(
    master_phil=master_phil)
  master_phil_str_overrides = """\
start_temperature_kelvin = 2500
final_temperature_kelvin = 300
number_of_cooling_steps = 44
number_of_time_steps = 1
time_step_pico_seconds = 0.001
minimization_max_iterations = None
"""
  phil_objects = [
    iotbx.phil.parse(input_string=master_phil_str_overrides)]
  pdb_files = []
  other_files = []
  for arg in args:
    if (os.path.isfile(arg)):
      if (iotbx.pdb.is_pdb_file(file_name=arg)):
        pdb_files.append(arg)
        arg = None
      else:
        try: phil_obj = iotbx.phil.parse(file_name=arg)
        except KeyboardInterrupt: raise
        except:
          other_files.append(arg)
        else:
          phil_objects.append(phil_obj)
        arg = None
    if (arg is not None):
      try: command_line_params = argument_interpreter.process(arg=arg)
      except KeyboardInterrupt: raise
      except: raise Sorry("Command-line argument not recognized: %s" % arg)
      else: phil_objects.append(command_line_params)
  params = master_phil.fetch(sources=phil_objects).extract()
  master_phil.format(params).show()
  print
  run_test(
    params=params,
    pdb_files=pdb_files,
    other_files=other_files,
    callback=callback)
  print format_cpu_times()

if (__name__ == "__main__"):
  run(args=sys.argv[1:])
