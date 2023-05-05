
import collections, datetime

import asyncio

import xml.etree.ElementTree as ET

from .events import EventException, getProperties, newSwitchVector


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

    def send_defVector(self, timestamp=None, timeout=0, message=''):
        "overridden in child classes"
        pass

    def __getitem__(self, membername):
        return self.members[membername]

    def __contains__(self, membername):
        return membername in self.members



class SwitchVector(PropertyVector):

    def __init__(self, name, label, group, perm, rule, state, switches):
        super().__init__(name, label, group, state)
        self.perm = perm
        self.rule = rule
        # this is a dictionary of switch name : switch
        self.members = {}
        for switch in switches:
            self.members[switch.name] = switch

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

    async def handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            if not self.enable:
                await asyncio.sleep(0.1)
                continue
            # test if any xml data has been received
            if not self.dataque:
                continue
            try:
                root = self.dataque.popleft()
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
                elif root.tag == "newSwitchVector":
                    if self._perm == 'ro':
                        # read only, cannot be changed
                        continue
                    # create event
                    event = newSwitchVector(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                continue

    def send_defVector(self, timestamp=None, timeout=0, message=''):
        """Sets defSwitchVector into writerque"""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
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
        self.members = {}
        for light in lights:
            self.members[light.name] = light

    async def handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            if not self.enable:
                await asyncio.sleep(0.1)
                continue
            # test if any xml data has been received
            if not self.dataque:
                continue
            try:
                root = self.dataque.popleft()
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                continue


    def send_defVector(self, timestamp=None, timeout=0, message=''):
        """Sets defLightVector into writerque"""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
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
