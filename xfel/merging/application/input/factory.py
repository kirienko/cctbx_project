from __future__ import division
from xfel.merging.application.input.file_loader import simple_file_loader
from xfel.merging.application.worker import factory as factory_base

""" Factory class for file loading. For now, supports simple file loading
Load balancing will come later using calculate_file_loadr """

class factory(factory_base):
  @staticmethod
  def from_parameters(params):
    """ Only one kind of loading supported at present, so construct a simple file loader """
    return [simple_file_loader(params)]
