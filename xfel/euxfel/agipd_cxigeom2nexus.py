from __future__ import absolute_import, division, print_function
from six.moves import range
import os
import h5py
import numpy as np
import subprocess
from read_geom import read_geom
from libtbx.phil import parse
from libtbx.utils import Sorry
import six

phil_scope = parse("""
  cxi_file = None
    .type = str
    .help = cheetah file used to read in image data(.cxi).
  geom_file = None
    .type = str
    .help = geometry file to be read in for AGIPD detector (.geom).
  detector_distance = None
    .type = float
    .help = AGIPD Detector distance
  wavelength = None
    .type = float
    .help = AGIPD wavelength override
  mode = vds cxi
    .type = choice
    .optional = False
    .help = Input data file format. VDS: virtual data set. CXI: \
            Cheetah file format.
""")


'''

This script creates a master nexus file by taking in as input a) a .cxi file and b) a .geom file
The cxi file is generated by cheetah after processing the raw images and doing appropriate gain corrections
The assumed parameters for the detector can be seen in the __init__ function and should be changed
if they are modified at EU XFEL in the future

'''


def get_git_revision_hash():
  definitions_path = os.path.join(os.path.dirname(sys.argv[0]), 'definitions')
  current_dir = os.getcwd()
  os.chdir(definitions_path)
  definitions_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip()
  os.chdir(current_dir)
  return definitions_hash.decode()


class agipd_cxigeom2nexus(object):
  def __init__(self, args):
    self.params_from_phil(args)
    if self.params.detector_distance == None:
      self.params.detector_distance = 177.0 # Set detector distance arbitrarily if nothing is provided
    self.hierarchy = read_geom(self.params.geom_file)
    self.n_quads = 4
    self.n_modules = 4
    self.n_asics =  8

  def params_from_phil(self, args):
    user_phil = []
    for arg in args:
      if os.path.isfile(arg):
        user_phil.append(parse(file_name=arg))
      else:
        try:
          user_phil.append(parse(arg))
        except Exception as e:
          raise Sorry("Unrecognized argument: %s"%arg)
    self.params = phil_scope.fetch(sources=user_phil).extract()

  def _create_scalar(self, handle,path,dtype,value):
    dataset = handle.create_dataset(path, (),dtype=dtype)
    dataset[()] = value

  def create_vector(self,handle, name, value, **attributes):
    handle.create_dataset(name, (1,), data = [value], dtype='f')
    for key,attribute in six.iteritems(attributes):
      handle[name].attrs[key] = attribute

  def create_nexus_master_file(self):

    '''
    Hierarchical structure of master nexus file. Format information available here
    http://download.nexusformat.org/sphinx/classes/base_classes/NXdetector_module.html#nxdetector-module
    --> entry
      --> data
      --> definition (leaf)
      --> instrument
      --> sample
    '''
    output_file_name = os.path.splitext(self.params.cxi_file)[0]+'_master.h5'
    f = h5py.File(output_file_name, 'w')
    entry = f.create_group('entry')
    entry.attrs['NX_class'] = 'NXentry'
    # --> definition
    definition_string = f"NXmx:{get_git_revision_hash()}"
    self._create_scalar(entry, 'definition', f'S{len(definition_string)}',np.string_(definition_string))
    # --> data
    data = entry.create_group('data')
    data.attrs['NX_class'] = 'NXdata'
    data_key = 'data'
    data[data_key] = h5py.ExternalLink(self.params.cxi_file, "entry_1/data_1/data")
    # --> sample
    sample = entry.create_group('sample')
    sample.attrs['NX_class'] = 'NXsample'
    beam = sample.create_group('beam')
    beam.attrs['NX_class'] = 'NXbeam'
    if self.params.wavelength is None:
      wavelengths = h5py.File(self.params.cxi_file, 'r')['instrument/photon_wavelength_A']
      beam.create_dataset('incident_wavelength', (1,), data=np.mean(wavelengths),dtype='f8')
    else:
      beam.create_dataset('incident_wavelength', (1,), data=self.params.wavelength,dtype='f8') # 9150
    beam['incident_wavelength'].attrs['units'] = 'angstrom'
    # --> instrument
    instrument = entry.create_group('instrument')
    instrument.attrs['NX_class'] = 'NXinstrument'
    agipd = instrument.create_group('AGIPD')
    agipd.attrs['NX_class'] = 'NXdetector_group'
    agipd.create_dataset('group_index', data = list(range(1,3)), dtype='i')
    data = [np.string_('AGIPD'), np.string_('ELE_D0')]
    agipd.create_dataset('group_names',(2,), data=data, dtype='S12')
    agipd.create_dataset('group_parent',(2,), data=[-1,1], dtype='i')
    agipd.create_dataset('group_type', (2,), data=[1,2], dtype='i')
    transformations = agipd.create_group('transformations')
    transformations.attrs['NX_class'] = 'NXtransformations'
    # Create AXIS leaves for RAIL, D0 and different hierarchical levels of detector
    self.create_vector(transformations, 'AXIS_RAIL', self.params.detector_distance, depends_on='.',
                       equipment='detector', equipment_component='detector_arm', transformation_type='translation',
                       units='mm', vector=(0., 0., 1.))
    self.create_vector(transformations, 'AXIS_D0', 0.0, depends_on='AXIS_RAIL', equipment='detector',
                       equipment_component='detector_arm', transformation_type='rotation', units='degrees',
                       vector=(0., 0., -1.), offset=self.hierarchy.local_origin, offset_units='mm')
    # Add 4 quadrants
    # Nexus coordiate system, into the board         AGIPD detector
    #      o --------> (+x)                             Q3=(12,13,14,15) Q0=(0,1,2,3)
    #      |                                                        o
    #      |                                            Q2=(8,9,10,11)   Q1=(4,5,6,7)
    #      v
    #     (+y)

    panels = []
    for q, quad in six.iteritems(self.hierarchy):
      for m, module in six.iteritems(quad):
        panels.extend([module[key] for key in module])
    fast = max([int(panel['max_fs']) for panel in panels])+1
    slow = max([int(panel['max_ss']) for panel in panels])+1
    pixel_size = panels[0]['pixel_size']
    assert [pixel_size == panels[i+1]['pixel_size'] for i in range(len(panels)-1)].count(False) == 0

    if self.params.mode == 'vds':
      quad_fast = fast
      quad_slow = slow * self.n_quads
      module_fast = quad_fast
      module_slow = quad_slow // self.n_quads
      asic_fast = module_fast
      asic_slow = module_slow // self.n_asics
    elif self.params.mode == 'cxi':
      quad_fast = fast
      quad_slow = slow // self.n_quads
      module_fast = quad_fast
      module_slow = quad_slow // self.n_modules
      asic_fast = module_fast
      asic_slow = module_slow // self.n_asics

    detector = instrument.create_group('ELE_D0')
    detector.attrs['NX_class']  = 'NXdetector'
    if 'mask' in h5py.File(self.params.cxi_file, 'r')['entry_1/data_1']:
      detector.create_dataset('pixel_mask_applied', (1,), data=[True], dtype='uint32')
      detector['pixel_mask'] = h5py.ExternalLink(self.params.cxi_file, "entry_1/data_1/mask")
    array_name = 'ARRAY_D0'

    alias = 'data'
    data_name = 'data'
    detector[alias] = h5py.SoftLink('/entry/data/%s'%data_name)

    for quad in range(self.n_quads):
      q_key = "q%d"%quad
      q_name = 'AXIS_D0Q%d'%quad
      quad_vector = self.hierarchy[q_key].local_origin.elems
      self.create_vector(transformations, q_name, 0.0, depends_on='AXIS_D0', equipment='detector',
                         equipment_component='detector_quad', transformation_type='rotation', units='degrees',
                         vector=(0., 0., -1.), offset=quad_vector, offset_units='mm')
      for module_num in range(self.n_modules):
        m_key = "p%d"%((quad*self.n_modules)+module_num)
        m_name = 'AXIS_D0Q%dM%d'%(quad, module_num)
        module_vector = self.hierarchy[q_key][m_key].local_origin.elems
        self.create_vector(transformations, m_name, 0.0, depends_on=q_name, equipment='detector',
                           equipment_component='detector_module', transformation_type='rotation', units='degrees',
                           vector=(0., 0., -1.), offset=module_vector, offset_units='mm')

        for asic_num in range(self.n_asics):
          a_key = "p%da%d"%((quad*self.n_modules)+module_num, asic_num)
          a_name = 'AXIS_D0Q%dM%dA%d'%(quad, module_num, asic_num)
          asic_vector = self.hierarchy[q_key][m_key][a_key]['local_origin'].elems
          self.create_vector(transformations, a_name, 0.0, depends_on=m_name, equipment='detector',
                             equipment_component='detector_asic', transformation_type='rotation', units='degrees',
                             vector=(0., 0., -1.), offset=asic_vector, offset_units='mm')

          asicmodule = detector.create_group(array_name+'Q%dM%dA%d'%(quad,module_num,asic_num))
          asicmodule.attrs['NX_class'] = 'NXdetector_module'
          if self.params.mode == 'vds':
            asicmodule.create_dataset('data_origin', (3,),
                                      data=[(quad * self.n_modules) + module_num, asic_slow * asic_num, 0], dtype='i')
            asicmodule.create_dataset('data_size', (3,), data=[1, asic_slow, asic_fast], dtype='i')
          elif self.params.mode == 'cxi':
            asicmodule.create_dataset('data_origin', (2,), data=[asic_slow*((quad*self.n_modules*self.n_asics) + (module_num*self.n_asics) + asic_num), 0],
                                                             dtype='i')
            asicmodule.create_dataset('data_size', (2,), data=[asic_slow, asic_fast], dtype='i')

          fast = self.hierarchy[q_key][m_key][a_key]['local_fast'].elems
          slow = self.hierarchy[q_key][m_key][a_key]['local_slow'].elems
          self.create_vector(asicmodule, 'fast_pixel_direction', pixel_size,
                             depends_on=transformations.name + '/AXIS_D0Q%dM%dA%d' % (quad, module_num, asic_num),
                             transformation_type='translation', units='mm', vector=fast, offset=(0., 0., 0.))
          self.create_vector(asicmodule, 'slow_pixel_direction', pixel_size,
                             depends_on=transformations.name + '/AXIS_D0Q%dM%dA%d' % (quad, module_num, asic_num),
                             transformation_type='translation', units='mm', vector=slow, offset=(0., 0., 0.))

    f.close()

if __name__ == '__main__':
  import sys
  nexus_helper = agipd_cxigeom2nexus(sys.argv[1:])
  nexus_helper.create_nexus_master_file()
