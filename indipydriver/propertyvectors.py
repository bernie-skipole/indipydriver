
import collections, datetime

import asyncio

import xml.etree.ElementTree as ET

from .events import EventException, getProperties, newSwitchVector, newTextVector, newBLOBVector, enableBLOB, newNumberVector
from .propertymembers import SwitchMember, LightMember, TextMember, NumberMember, BLOBMember

class PropertyVector(collections.UserDict):
    "Parent class of SwitchVector etc.."

    def __init__(self, name, label, group, state):
        super().__init__()
        self.name = name
        self.label = label
        self.group = group
        self.state = state
        # if self.enable is False, this property ignores incoming traffic
        # and (apart from delProperty) does not transmit anything
        self.enable = True
        # the device places data in this dataque
        # for the vector to act upon
        self.dataque = collections.deque()

        # this will be set when the device is initialised
        self.devicename = None

        # this will be set when the driver asyncrun is run
        self.driver = None

        self.members = {}


    @property
    def device(self):
        return self.driver.devices[self.devicename]

    def send_device_message(self, message="", timestamp=None):
        "Send message associated with the device this vector belongs to"
        self.device.send_device_message(message, timestamp)

    def send_message(self, message="", timestamp=None):
        "Send system wide message - without device name"
        self.driver.send_message(message, timestamp)

    def send_delProperty(self, message="", timestamp=None):
        "Send delProperty with this device and property, set self.enable to False"
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp given in send_delProperty must be a datetime.datetime object")
        xmldata = ET.Element('delProperty')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        self.driver.writerque.append(xmldata)
        self.enable = False

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

    def send_defVector(self, timestamp=None, timeout=0, message=''):
        "overridden in child classes"
        pass

    def valuedict(self):
        return {membername:member.membervalue for membername,member in self.members.values()}

    def __setitem__(self, membername, value):
        self.members[membername].membervalue = value
        # setting value into self.members[membername].membervalue may
        # include some changes (number format) so set self.data[membername]
        # to the resultant self.members[membername].membervalue
        self.data[membername] = self.members[membername].membervalue


class SwitchVector(PropertyVector):

    def __init__(self, name, label, group, perm, rule, state, switchmembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        self.rule = rule
        # this is a dictionary of switch name : switchmember
        self.members = {}
        for switch in switchmembers:
            if not isinstance(switch, SwitchMember):
                raise TypeError("Members of a SwitchVector must all be SwitchMembers")
            self.members[switch.name] = switch
            self.data[switch.name] = switch.membervalue

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
            # test if any xml data has been received
            if not self.dataque:
                continue
            try:
                root = self.dataque.popleft()
                if not self.device.enable:
                    continue
                if not self.enable:
                    continue
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
        if not self.device.enable:
            return
        if not self.enable:
            return
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
        if not self.device.enable:
            return
        if not self.enable:
            return
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
            if not isinstance(light, LightMember):
                raise TypeError("Members of a LightVector must all be LightMembers")
            self.members[light.name] = light
            self.data[light.name] = light.membervalue

    async def handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            # test if any xml data has been received
            if not self.dataque:
                continue
            try:
                root = self.dataque.popleft()
                if not self.device.enable:
                    continue
                if not self.enable:
                    continue
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
        if not self.device.enable:
            return
        if not self.enable:
            return
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
        if not self.device.enable:
            return
        if not self.enable:
            return
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
            if not isinstance(text, TextMember):
                raise TypeError("Members of a TextVector must all be TextMembers")
            self.members[text.name] = text
            self.data[text.name] = text.membervalue

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
            # test if any xml data has been received
            if not self.dataque:
                continue
            try:
                root = self.dataque.popleft()
                if not self.device.enable:
                    continue
                if not self.enable:
                    continue
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
        if not self.device.enable:
            return
        if not self.enable:
            return
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
        if not self.device.enable:
            return
        if not self.enable:
            return
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



class NumberVector(PropertyVector):

    def __init__(self, name, label, group, perm, state, numbermembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        # this is a dictionary of number name : numbermember
        self.members = {}
        for number in numbermembers:
            if not isinstance(number, NumberMember):
                raise TypeError("Members of a NumberVector must all be NumberMembers")
            self.members[number.name] = number
            self.data[number.name] = number.membervalue

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
            # test if any xml data has been received
            if not self.dataque:
                continue
            try:
                root = self.dataque.popleft()
                if not self.device.enable:
                    continue
                if not self.enable:
                    continue
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
                elif root.tag == "newNumberVector":
                    if self._perm == 'ro':
                        # read only, cannot be changed
                        continue
                    # create event
                    event = newNumberVector(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                continue

    def send_defVector(self, timestamp=None, timeout=0, message=''):
        """Sets defNumberVector into writerque for transmission"""
        if not self.device.enable:
            return
        if not self.enable:
            return
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('defNumberVector')
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
        for number in self.members.values():
            xmldata.append(number.defnumber())
        self.driver.writerque.append(xmldata)

    def send_setVector(self, timestamp=None, timeout=0, message=''):
        """Sets setNumberVector into writerque for transmission"""
        if not self.device.enable:
            return
        if not self.enable:
            return
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('setNumberVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("state", self.state)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        xmldata.set("timeout", str(timeout))
        if message:
            xmldata.set("message", message)
        for number in self.members.values():
            xmldata.append(number.onenumber())
        self.driver.writerque.append(xmldata)


class BLOBVector(PropertyVector):

    def __init__(self, name, label, group, perm, state, blobmembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        # this is a dictionary of blob name : blobmember
        self.members = {}
        for blob in blobmembers:
            if not isinstance(blob, BLOBMember):
                raise TypeError("Members of a BLOBVector must all be BLOBMembers")
            self.members[blob.name] = blob
            self.data[blob.name] = blob.membervalue

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
            # test if any xml data has been received
            if not self.dataque:
                continue
            try:
                root = self.dataque.popleft()
                if not self.device.enable:
                    continue
                if not self.enable:
                    continue
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
                elif root.tag == "enableBLOB":
                    # create event
                    event = enableBLOB(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
                elif root.tag == "newBLOBVector":
                    if self._perm == 'ro':
                        # read only, cannot be changed
                        continue
                    # create event
                    event = newBLOBVector(self.devicename, self.name, self, root)
                    await self.driver.eventaction(event)
                    continue
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                continue

    def send_defVector(self, timestamp=None, timeout=0, message=''):
        """Sets defBLOBVector into writerque for transmission"""
        if not self.device.enable:
            return
        if not self.enable:
            return
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('defBLOBVector')
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
        for blob in self.members.values():
            xmldata.append(blob.defblob())
        self.driver.writerque.append(xmldata)

    def send_setVector(self, timestamp=None, timeout=0, message=''):
        """Sets setBLOBVector into writerque for transmission"""
        if not self.device.enable:
            return
        if not self.enable:
            return
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp must be a datetime.datetime object")
        xmldata = ET.Element('setBLOBVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("state", self.state)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        xmldata.set("timeout", str(timeout))
        if message:
            xmldata.set("message", message)
        for blob in self.members.values():
            xmldata.append(blob.oneblob())
        self.driver.writerque.append(xmldata)
