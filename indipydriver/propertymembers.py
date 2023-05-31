
import collections

import asyncio

from datetime import datetime

import xml.etree.ElementTree as ET

from base64 import standard_b64encode

class PropertyMember:
    "Parent class of SwitchMember etc"

    def __init__(self, name, label=None):
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        self._membervalue = None
        # self.changed is a flag to indicate the value has changed
        # initially start with all values have changed
        self.changed = True

    def checkvalue(self, value, allowed):
        "allowed is a list of values, checks if value is in it"
        if value not in allowed:
            raise ValueError(f"Value \"{value}\" is not one of {str(allowed).strip('[]')}")
        return value


class SwitchMember(PropertyMember):
    """A SwitchMember can only have one of 'On' or 'Off' values"""

    def __init__(self, name, label=None):
        super().__init__(name, label)
        # membervalue should be either 'Off' or 'On'
        self._membervalue = 'Off'

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        newvalue = self.checkvalue(value, ['On', 'Off'])
        if self._membervalue != newvalue:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = newvalue

    def defswitch(self):
        """Returns a defSwitch"""
        xmldata = ET.Element('defSwitch')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._membervalue
        return xmldata

    def oneswitch(self):
        """Returns xml of a oneSwitch"""
        xmldata = ET.Element('oneSwitch')
        xmldata.set("name", self.name)
        xmldata.text = self._membervalue
        return xmldata


class LightMember(PropertyMember):
    """A LightMember can only have one of 'Idle', 'Ok', 'Busy' or 'Alert' values"""

    def __init__(self, name, label=None):
        super().__init__(name, label)
        self._membervalue = 'Idle'

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        newvalue = self.checkvalue(value, ['Idle','Ok','Busy','Alert'])
        if self._membervalue != newvalue:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = newvalue

    def deflight(self):
        """Returns xml of a defLight"""
        xmldata = ET.Element('defLight')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._membervalue
        return xmldata

    def onelight(self):
        """Returns xml of a oneLight"""
        xmldata = ET.Element('oneLight')
        xmldata.set("name", self.name)
        xmldata.text = self._membervalue
        return xmldata


class TextMember(PropertyMember):
    """Contains a text string"""

    def __init__(self, name, label=None):
        super().__init__(name, label)
        self._membervalue = ''

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if self._membervalue != value:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = value

    def deftext(self):
        """Returns a defText"""
        xmldata = ET.Element('defText')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self.membervalue
        return xmldata

    def onetext(self):
        """Returns xml of a oneText"""
        xmldata = ET.Element('oneText')
        xmldata.set("name", self.name)
        xmldata.text = self.membervalue
        return xmldata


class NumberMember(PropertyMember):
    """Contains a number, the attributes inform the client how the number should be
       displayed.

       format is a C printf style format, for example %7.2f means the number string will
       have seven characters (including the decimal point as a character and leading
       spaces will be inserted if necessary), and two decimal digits after the decimal point.

       min is the minimum value

       max is the maximum, if min is equal to max, the client should ignore these.

       step is incremental step values, set to zero if not used.

       If the member value is set as a string - that is how the number will be placed in the
       xml protocol.

       If set as a float, the string placed into the xml will be formatted according to the given format.
    """

    def __init__(self, name, label=None, format='', min=0, max=0, step=0):
        super().__init__(name, label)
        self.format = format
        self.min = min
        self.max = max
        self.step = step
        self._membervalue = min

        # If membervalue, min, max step are given as strings, they are assumed to
        # be correctly formatted and used in the xml directly.
        # if given as integers or floats, they are formatted using the format string

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if self._membervalue != value:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = value

    def format_number(self, value):
        """This takes a float, and returns a formatted string
        """
        if (not self.format.startswith("%")) or (not self.format.endswith("m")):
            return self.format % value
        # sexagesimal format
        if value<0:
            negative = True
            value = abs(value)
        else:
            negative = False
        # number list will be degrees, minutes, seconds
        number_list = [0,0,0]
        if isinstance(value, int):
            number_list[0] = value
        else:
            # get integer part and fraction part
            fractdegrees, degrees = math.modf(value)
            number_list[0] = int(degrees)
            mins = 60*fractdegrees
            fractmins, mins = math.modf(mins)
            number_list[1] = int(mins)
            number_list[2] = 60*fractmins

        # so number list is a valid degrees, minutes, seconds
        # degrees
        if negative:
            number = f"-{number_list[0]}:"
        else:
            number = f"{number_list[0]}:"
        # format string is of the form  %<w>.<f>m
        w,f = self.format.split(".")
        w = w.lstrip("%")
        f = f.rstrip("m")
        if (f == "3") or (f == "5"):
            # no seconds, so create minutes value
            minutes = float(number_list[1]) + number_list[2]/60.0
            if f == "5":
                number += f"{minutes:04.1f}"
            else:
                number += f"{minutes:02.0f}"
        else:
            number += f"{number_list[1]:02d}:"
            seconds = float(number_list[2])
            if f == "6":
                number += f"{seconds:02.0f}"
            elif f == "8":
                number += f"{seconds:04.1f}"
            else:
                number += f"{seconds:05.2f}"

        # w is the overall length of the string, prepend with spaces to make the length up to w
        w = int(w)
        l = len(number)
        if w>l:
            number = " "*(w-l) + number
        return number

    def defnumber(self):
        """Returns a defNumber"""
        xmldata = ET.Element('defNumber')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("format", self.format)

        if isinstance(self.min, str):
            xmldata.set("min", self.min)
        else:
            xmldata.set("min", self.format_number(self.min))

        if isinstance(self.max, str):
            xmldata.set("max", self.max)
        else:
            xmldata.set("max", self.format_number(self.max))

        if isinstance(self.step, str):
            xmldata.set("step", self.step)
        else:
            xmldata.set("step", self.format_number(self.step))

        if isinstance(self._membervalue, str):
            xmldata.text = self._membervalue
        else:
            xmldata.text = self.format_number(self._membervalue)
        return xmldata

    def onenumber(self):
        """Returns xml of a oneNumber"""
        xmldata = ET.Element('oneNumber')
        xmldata.set("name", self.name)
        if isinstance(self._membervalue, str):
            xmldata.text = self._membervalue
        else:
            xmldata.text = self.format_number(self._membervalue)
        return xmldata


class BLOBMember(PropertyMember):
    """Contains a 'binary large object' such as an image, the value should be
       a bytes object.

       blobsize is the size of the BLOB before any compression, if left at
       zero, the length of the BLOB will be used.

       The BLOB format should be a string describing the BLOB, such as .jpeg
    """

    def __init__(self, name, label=None, blobsize = 0, blobformat = ''):
        super().__init__(name, label)
        self._membervalue = b''
        self.blobsize = blobsize
        self.blobformat = blobformat

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if not isinstance(value, bytes):
            raise ValueError("The given BLOB value must be a bytes object")
        # don't test for equality here since the byte data may be large
        # just assume setting it implies a change
        self.changed = True
        self._membervalue = value

    def defblob(self):
        """Returns a defBlob, does not contain a membervalue"""
        xmldata = ET.Element('defBlob')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        return xmldata

    def oneblob(self):
        """Returns xml of a oneBLOB"""
        xmldata = ET.Element('oneBLOB')
        xmldata.set("name", self.name)
        if not self.blobsize:
            self.blobsize = len(self.membervalue)
        xmldata.set("size", str(self.blobsize))
        xmldata.set("format", self.blobformat)
        xmldata.text = standard_b64encode(self.membervalue).decode('ascii')
        return xmldata
