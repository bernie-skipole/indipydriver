
import collections, datetime

import asyncio

import xml.etree.ElementTree as ET

from .events import EventException, getProperties, newSwitchVector, newTextVector


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

    def __init__(self, name, label, group, perm, rule, state, switchmembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        self.rule = rule
        # this is a dictionary of switch name : switchmember
        self.members = {}
        for switch in switchmembers:
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
        """Sets defSwitchVector into writerque for transmission"""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('defSwitchVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("group", self.group)
        xmldata.set("state", self.state)
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

    def send_setVector(self, timestamp=None, timeout=0, message=''):
        """Sets setSwitchVector into writerque for transmission"""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('setSwitchVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("state", self.state)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        xmldata.set("timeout", str(timeout))
        if message:
            xmldata.set("message", message)
        for switch in self.members.values():
            xmldata.append(switch.oneswitch())
        self.driver.writerque.append(xmldata)



class LightVector(PropertyVector):

    def __init__(self, name, label, group, state, lightmembers):
        super().__init__(name, label, group, state)
        # this is a dictionary of light name : lightmember
        self.members = {}
        for light in lightmembers:
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
        """Sets defLightVector into writerque for transmission"""
        # Note timeout is not used
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


    def send_setVector(self, timestamp=None, timeout=0, message=''):
        """Sets setLightVector into writerque for transmission"""
        # Note timeout is not used
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('setLightVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("state", self.state)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        for light in self.members.values():
            xmldata.append(light.onelight())
        self.driver.writerque.append(xmldata)


class TextVector(PropertyVector):

    def __init__(self, name, label, group, perm, state, textmembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        # this is a dictionary of text name : textmember
        self.members = {}
        for text in textmembers:
            self.members[text.name] = text

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

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
                elif root.tag == "newTextVector":
                    if self._perm == 'ro':
                        # read only, cannot be changed
                        continue
                    # create event
                    event = newTextVector(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                continue

    def send_defVector(self, timestamp=None, timeout=0, message=''):
        """Sets defTextVector into writerque for transmission"""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('defTextVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("group", self.group)
        xmldata.set("state", self.state)
        xmldata.set("perm", self.perm)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        xmldata.set("timeout", str(timeout))
        if message:
            xmldata.set("message", message)
        for text in self.members.values():
            xmldata.append(text.deftext())
        self.driver.writerque.append(xmldata)

    def send_setVector(self, timestamp=None, timeout=0, message=''):
        """Sets setTextVector into writerque for transmission"""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('setTextVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("state", self.state)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        xmldata.set("timeout", str(timeout))
        if message:
            xmldata.set("message", message)
        for text in self.members.values():
            xmldata.append(text.onetext())
        self.driver.writerque.append(xmldata)
