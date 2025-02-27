
import sys

from .ipydriver import IPyDriver, Device
from .propertyvectors import SwitchVector, LightVector, TextVector, BLOBVector, NumberVector
from .propertymembers import SwitchMember, LightMember, TextMember, BLOBMember, NumberMember, getfloat
from .events import getProperties, enableBLOB, newSwitchVector, newTextVector, newNumberVector, newBLOBVector, Message, delProperty, defSwitchVector, defTextVector, defNumberVector, defLightVector, defBLOBVector, setSwitchVector, setTextVector, setNumberVector, setLightVector, setBLOBVector
from .ipyserver import IPyServer

if sys.version_info < (3, 10):
    raise ImportError('indipyterm requires Python >= 3.10')

version = "2.1.3"
