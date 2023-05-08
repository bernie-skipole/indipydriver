
import collections

import asyncio

from datetime import datetime

import xml.etree.ElementTree as ET

class PropertyMember:
    "Parent class of SwitchMember etc"

    def checkvalue(self, value, allowed):
        "allowed is a list of values, checks if value is in it"
        if value not in allowed:
            raise ValueError(f"Value \"{value}\" is not one of {str(allowed).strip('[]')}")
        return value


class SwitchMember(PropertyMember):

    def __init__(self, name, label=None):
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        # switchvalue should be either 'Off' or 'On'
        self._switchvalue = 'Off'

    @property
    def switchvalue(self):
        return self._switchvalue

    @switchvalue.setter
    def switchvalue(self, value):
        self._switchvalue = self.checkvalue(value, ['On', 'Off'])

    def defswitch(self):
        """Returns a defSwitch"""
        xmldata = ET.Element('defSwitch')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._switchvalue
        return xmldata

    def oneswitch(self, switchvalue=None):
        """Returns xml of a oneSwitch, sets switchvalue
           or if None the current value is unchanged"""
        if switchvalue:
            self.switchvalue = switchvalue
        xmldata = ET.Element('oneSwitch')
        xmldata.set("name", self.name)
        xmldata.text = self._switchvalue
        return xmldata



class LightMember(PropertyMember):

    def __init__(self, name, label=None):
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        # lightvalue should be one of Idle|Ok|Busy|Alert
        self._lightvalue = 'Idle'

    @property
    def lightvalue(self):
        return self._lightvalue

    @lightvalue.setter
    def lightvalue(self, value):
        self._lightvalue = self.checkvalue(value, ['Idle','Ok','Busy','Alert'])

    def deflight(self):
        """Returns a defLight"""
        xmldata = ET.Element('defLight')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._lightvalue
        return xmldata

    def onelight(self, lightvalue=None):
        """Returns xml of a oneLight, sets lightvalue
           or if None the current value is unchanged"""
        if lightvalue:
            self.lightvalue = lightvalue
        xmldata = ET.Element('oneLight')
        xmldata.set("name", self.name)
        xmldata.text = self._lightvalue
        return xmldata


class TextMember(PropertyMember):

    def __init__(self, name, label=None):
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        self.textvalue = ''

    def deftext(self):
        """Returns a defText"""
        xmldata = ET.Element('defText')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self.textvalue
        return xmldata

    def onetext(self, textvalue=None):
        """Returns xml of a oneText, sets textvalue
           or if None the current value is unchanged"""
        if textvalue:
            self.textvalue = textvalue
        xmldata = ET.Element('oneText')
        xmldata.set("name", self.name)
        xmldata.text = self.textvalue
        return xmldata


class NumberMember(PropertyMember):

    def __init__(self, name, label=None, format='', min='', max='', step='0'):
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        self.format = format
        self.min = min
        self.max = max
        self.step = step
        self._numbervalue = None

        # If numbervalue, min, max step are given as strings, they are assumed to
        # be correctly formatted and used in the xml directly.
        # if given as integers or floats, they are formatted using the format string


    @property
    def numbervalue(self):
        return self._numbervalue

    @numbervalue.setter
    def numbervalue(self, value):
        if isinstance(value, str):
            self._numbervalue = value
        else:
            self._numbervalue = self.format_number(value)

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
        xmldata.text = self._numbervalue
        return xmldata

    def onenumber(self, numbervalue=None):
        """Returns xml of a oneNumber, sets numbervalue
           or if None the current value is unchanged"""
        if not numbervalue is None:
            self.numbervalue = numbervalue
        xmldata = ET.Element('oneNumber')
        xmldata.set("name", self.name)
        xmldata.text = self._numbervalue
        return xmldata


class BLOBMember(PropertyMember):

    def __init__(self, name, label=None):
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        self.blobvalue = ''
        self.blobsize = ''
        self.blobformat = ''

    def defblob(self):
        """Returns a defBlob, does not contain a blobvalue"""
        xmldata = ET.Element('defBlob')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        return xmldata

    def oneblob(self, blobvalue=None):
        """Returns xml of a oneBLOB, sets blobvalue
           or if None the current value is unchanged"""
        if blobvalue:
            self.blobvalue = blobvalue
        xmldata = ET.Element('oneBLOB')
        xmldata.set("name", self.name)
        xmldata.set("size", str(self.blobsize))
        xmldata.set("format", self.blobformat)
        xmldata.text = self.blobvalue
        return xmldata
