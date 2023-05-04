
import collections

import asyncio

from datetime import datetime

import xml.etree.ElementTree as ET



class SwitchMember:

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
        if self._switchstate == 'On':
            return True
        else:
            return False

    @switchstate.setter
    def switchstate(self, value):
        if value:
            self._switchstate = 'On'
        else:
            self._switchstate = 'Off'

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
