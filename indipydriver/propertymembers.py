
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

    def checkvalue(self, value, allowed):
        "allowed is a list of values, checks if value is in it"
        if value not in allowed:
            raise ValueError(f"Value \"{value}\" is not one of {str(allowed).strip('[]')}")
        return value


class SwitchMember(PropertyMember):

    def __init__(self, name, label=None):
        super().__init__(name, label)
        # membervalue should be either 'Off' or 'On'
        self._membervalue = 'Off'

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        self._membervalue = self.checkvalue(value, ['On', 'Off'])

    def defswitch(self):
        """Returns a defSwitch"""
        xmldata = ET.Element('defSwitch')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._membervalue
        return xmldata

    def oneswitch(self, membervalue=None):
        """Returns xml of a oneSwitch, sets membervalue
           or if None the current value is unchanged"""
        if membervalue:
            self.membervalue = membervalue
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
        self._membervalue = self.checkvalue(value, ['Idle','Ok','Busy','Alert'])

    def deflight(self):
        """Returns xml of a defLight"""
        xmldata = ET.Element('defLight')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._membervalue
        return xmldata

    def onelight(self, membervalue=None):
        """Returns xml of a oneLight, sets membervalue
           or if None the current value is unchanged"""
        if membervalue:
            self.membervalue = membervalue
        xmldata = ET.Element('oneLight')
        xmldata.set("name", self.name)
        xmldata.text = self._membervalue
        return xmldata


class TextMember(PropertyMember):

    def __init__(self, name, label=None):
        super().__init__(name, label)
        self.membervalue = ''

    def deftext(self):
        """Returns a defText"""
        xmldata = ET.Element('defText')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self.membervalue
        return xmldata

    def onetext(self, membervalue=None):
        """Returns xml of a oneText, sets membervalue
           or if None the current value is unchanged"""
        if membervalue:
            self.membervalue = membervalue
        xmldata = ET.Element('oneText')
        xmldata.set("name", self.name)
        xmldata.text = self.membervalue
        return xmldata


class NumberMember(PropertyMember):

    def __init__(self, name, label=None, format='', min=0, max=0, step=0):
        super().__init__(name, label)
        self.format = format
        self.min = min
        self.max = max
        self.step = step
        self._membervalue = None

        # If membervalue, min, max step are given as strings, they are assumed to
        # be correctly formatted and used in the xml directly.
        # if given as integers or floats, they are formatted using the format string


    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if isinstance(value, str):
            self._membervalue = value
        else:
            self._membervalue = self.format_number(value)

    @property
    def min(self):
        return self._min

    @min.setter
    def min(self, value):
        if isinstance(value, str):
            self._min = value
        else:
            self._min = self.format_number(value)

    @property
    def max(self):
        return self._max

    @max.setter
    def max(self, value):
        if isinstance(value, str):
            self._max = value
        else:
            self._max = self.format_number(value)

    @property
    def step(self):
        return self._step

    @step.setter
    def step(self, value):
        if isinstance(value, str):
            self._step = value
        else:
            self._step = self.format_number(value)

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
        xmldata.set("min", self._min)
        xmldata.set("max", self._max)
        xmldata.set("step", self._step)
        xmldata.text = self._membervalue
        return xmldata

    def onenumber(self, membervalue=None):
        """Returns xml of a oneNumber, sets membervalue
           or if None the current value is unchanged"""
        if not membervalue is None:
            self.membervalue = membervalue
        xmldata = ET.Element('oneNumber')
        xmldata.set("name", self.name)
        xmldata.text = self._membervalue
        return xmldata


class BLOBMember(PropertyMember):

    def __init__(self, name, label=None):
        super().__init__(name, label)
        self._membervalue = b''
        self.blobsize = ''
        self.blobformat = ''

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if not isinstance(value, bytes):
            raise ValueError("The given BLOB value must be a bytes object")
        self._membervalue = value

    def defblob(self):
        """Returns a defBlob, does not contain a membervalue"""
        xmldata = ET.Element('defBlob')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        return xmldata

    def oneblob(self, membervalue=None):
        """Returns xml of a oneBLOB, sets membervalue
           or if None the current value is unchanged"""
        if membervalue:
            self.membervalue = membervalue
        xmldata = ET.Element('oneBLOB')
        xmldata.set("name", self.name)
        if not self.blobsize:
            self.blobsize = len(self.membervalue)
        xmldata.set("size", str(self.blobsize))
        xmldata.set("format", self.blobformat)
        xmldata.text = standard_b64encode(self.membervalue).decode('ascii')
        return xmldata
