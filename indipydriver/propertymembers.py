
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
        self.numbervalue = ''

    def defnumber(self):
        """Returns a defNumber"""
        xmldata = ET.Element('defNumber')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("format", self.format)
        xmldata.set("min", self.min)
        xmldata.set("max", self.max)
        xmldata.set("step", self.step)
        xmldata.text = self.numbervalue
        return xmldata

    def onenumber(self, numbervalue=None):
        """Returns xml of a oneNumber, sets numbervalue
           or if None the current value is unchanged"""
        if numbervalue:
            self.numbervalue = numbervalue
        xmldata = ET.Element('oneNumber')
        xmldata.set("name", self.name)
        xmldata.text = self.numbervalue
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
