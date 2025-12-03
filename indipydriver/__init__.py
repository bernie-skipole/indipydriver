
import sys

from .ipydriver import IPyDriver, Device
from .propertyvectors import SwitchVector, LightVector, TextVector, BLOBVector, NumberVector
from .propertymembers import SwitchMember, LightMember, TextMember, BLOBMember, NumberMember, getfloat
from .events import getProperties, newSwitchVector, newTextVector, newNumberVector, newBLOBVector, Message, delProperty, defSwitchVector, defTextVector, defNumberVector, defLightVector, defBLOBVector, setSwitchVector, setTextVector, setNumberVector, setLightVector, setBLOBVector


if sys.version_info < (3, 11):
    raise ImportError('indipydriver requires Python >= 3.11')

version = "3.0.4"


__all__ = ["version", "IPyDriver", "Device", "getfloat",
           "SwitchVector", "LightVector", "TextVector", "BLOBVector", "NumberVector",
           "SwitchMember", "LightMember", "TextMember", "BLOBMember", "NumberMember",
           "getProperties", "newSwitchVector", "newTextVector", "newNumberVector", "newBLOBVector",
           "Message", "delProperty", "defSwitchVector", "defTextVector", "defNumberVector", "defLightVector", "defBLOBVector",
           "setSwitchVector", "setTextVector", "setNumberVector", "setLightVector", "setBLOBVector"]
