
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
        # switchstate should be either 'Off' or 'On'
        self._switchstate = 'Off'

    @property
    def switchstate(self):
        return self._switchstate

    @switchstate.setter
    def switchstate(self, value):
        self._switchstate = self.checkvalue(value, ['On', 'Off'])


    def defswitch(self):
        """Returns a defSwitch"""
        xmldata = ET.Element('defSwitch')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._switchstate
        return xmldata

    def oneswitch(self, switchstate=None):
        """Returns xml of a oneSwitch, switchstate is True, False or not giben"""
        if switchstate is None:
            switchstate = self._switchstate
        else:
            self.switchstate = switchstate
        xmldata = ET.Element('oneSwitch')
        xmldata.set("name", self.name)
        xmldata.text = self._switchstate
        return xmldata



class LightMember(PropertyMember):

    def __init__(self, name, label=None):
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        # lightstate should be one of Idle|Ok|Busy|Alert
        self._lightstate = 'Idle'

    @property
    def lightstate(self):
        return self._lightstate

    @lightstate.setter
    def lightstate(self, value):
        self._lightstate = self.checkvalue(value, ['Idle','Ok','Busy','Alert'])

    def deflight(self):
        """Returns a defLight"""
        xmldata = ET.Element('defLight')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._lightstate
        return xmldata
