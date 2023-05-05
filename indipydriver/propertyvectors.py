
import collections, datetime

import asyncio

import xml.etree.ElementTree as ET

from .events import getProperties


class PropertyVector:
    "Parent class of SwitchVector etc.."

    def __init__(self, name, label, group, state):
        self.name = name
        self.label = label
        self.group = group
        self.state = state
        # if self.enable is False, this property is dormant
        self.enable = True
        # the device places data in this dataque
        # for the vector to act upon
        self.dataque = collections.deque()

        # this will be set when the driver asyncrun is run
        self.driver = None

        self.members = {}

    def checkvalue(self, value, allowed):
        "allowed is a list of values, checks if value is in it"
        if value not in allowed:
            raise ValueError(f"Value \"{value}\" is not one of {str(allowed).strip('[]')}")
        return value

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = self.checkvalue(value, ['Idle','Ok','Busy','Alert'])


    def set_propertyquedict(self, propertyquedict):
        """Every PropertyVector has access to the dataque of
           all other propertyvectors via this dictionary, which is
           a name:dataque dictionary"""
        self.propertyquedict = propertyquedict


    def send_defVector(timestamp, timeout, message):
        "overridden in child classes"
        pass

    def __getitem__(self, membername):
        return self.members[membername]


    async def handler(self):
        """Check received data and take action"""
        # xmldata to be sent is to be generated here
        while True:
            await asyncio.sleep(0)
            if not self.enable:
                await asyncio.sleep(0.1)
                continue
            # test if any xml data has been received
            if not self.dataque:
                continue
            root = self.dataque.popleft()
            if root.tag == "getProperties":
                # create event
                event = getProperties(self.devicename, self.name, self)
                await self.driver.eventaction(event)
                continue
            else:
                # further elifs should go here
                pass


class SwitchVector(PropertyVector):

    def __init__(self, name, label, group, perm, rule, state, switches):
        super().__init__(name, label, group, state)
        self.perm = perm
        self.rule = rule
        # this is a dictionary of switch name : switch
        self.members = {switch.name:switch for switch in switches}


    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    @property
    def rule(self):
        return self._rule

    @rule.setter
    def rule(self, value):
        self._rule = self.checkvalue(value, ['OneOfMany','AtMostOne','AnyOfMany'])

    def send_defVector(self, timestamp, timeout, message):
        """Sets defSwitchVector into writerque"""
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('defSwitchVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("group", self.group)
        xmldata.set("perm", self.perm)
        xmldata.set("rule", self.rule)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        xmldata.set("timeout", str(timeout))
        if message:
            xmldata.set("message", message)
        for switch in self.members.values():
            xmldata.append(switch.defswitch())
        self.driver.writerque.append(xmldata)



class LightVector(PropertyVector):

    def __init__(self, name, label, group, state, lights):
        super().__init__(name, label, group, state)
        # this is a dictionary of light name : light
        self.members = {light.name:light for light in lights}


    def send_defVector(self, timestamp, timeout, message):
        """Sets defLightVector into writerque"""
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('defLightVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("group", self.group)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        for light in self.members.values():
            xmldata.append(light.deflight())
        self.driver.writerque.append(xmldata)
