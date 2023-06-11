
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
        self.dataque = asyncio.Queue(4)

        # this will be set when the device is initialised
        self.devicename = None

        # this will be set when the driver asyncrun is run
        self.driver = None

    @property
    def device(self):
        return self.driver.devices[self.devicename]

    async def send_delProperty(self, message="", timestamp=None):
        """Informs the client this vector is not available, it also sets an 'enable' attribute to
           False, which stops any data being transmitted between the client and this property vector.

           Setting vector.enable to True re-enables communications.

           The message argument is any appropriate string which the client could display to the user.

           The timestamp should be either None or a datetime.datetime object. If the timestamp is None
           a datetime.datetime.utcnow() value will be inserted."""
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
        await self.driver.writerque.put(xmldata)
        self.enable = False
        for member in self.data.values():
            # set all members as changed, so when re-enabled, all values are ready to be sent again
            member.changed = True

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

    def __setitem__(self, membername, value):
        self.data[membername].membervalue = value

    def __getitem__(self, membername):
        return self.data[membername].membervalue


class SwitchVector(PropertyVector):

    """A SwitchVector sends and receives one or more members with values 'On' or 'Off'. It
       also has the extra attribute 'rule' which can be one of 'OneOfMany', 'AtMostOne', 'AnyOfMany'.
       These are hints to the client how to display the switches in the vector.

       OneOfMany - of the SwitchMembers in this vector, one (and only one) must be On.

       AtMostOne - of the SwitchMembers in this vector, one or none can be On.

       AnyOfMany - multiple switch members can be On.
       """

    def __init__(self, name, label, group, perm, rule, state, switchmembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        self.rule = rule
        # self.data is a dictionary of switch name : switchmember
        for switch in switchmembers:
            if not isinstance(switch, SwitchMember):
                raise TypeError("Members of a SwitchVector must all be SwitchMembers")
            self.data[switch.name] = switch

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

    async def _handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            try:
                root = await self.dataque.get()
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
                elif root.tag == "newSwitchVector":
                    # create event
                    event = newSwitchVector(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                pass
            self.dataque.task_done()


    async def send_defVector(self, message='', timestamp=None, timeout='0'):
        """Transmits the vector definition (defSwitchVector) to the client.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which
           case a datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string of a
           numeric value indicating to the client how long this data is valid.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        for switch in self.data.values():
            xmldata.append(switch.defswitch())
            # after a defswitch sent, assume new client connection, and set all members as changed
            # so they will all be included in the first 'send_setVector'
            switch.changed = True
        await self.driver.writerque.put(xmldata)

    async def send_setVector(self, message='', timestamp=None, timeout='0', allvalues=True):
        """Transmits the vector (setSwitchVector) and members with their values to the client.
           Typically the vector 'state' should be set, and any changed member value prior to
           transmission.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which case a
           datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string value indicating
           to the client how long this data is valid.

           If allvalues is True, all values are sent.

           If allvalues is False, only values that have changed will be sent, saving bandwidth.
           If no values have changed, the vector will not be sent, if you need to ensure the
           vector message, state or time values are sent to the client, then use the more
           explicit send_setVectorMembers method instead.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        # for rule 'OneOfMany' the standard indicates 'Off' should precede 'On'
        # so make all 'On' values last
        Offswitches = (switch for switch in self.data.values() if switch.membervalue == 'Off')
        Onswitches = (switch for switch in self.data.values() if switch.membervalue == 'On')
        # set a flag to test if at least one member is included
        membersincluded = False
        for switch in Offswitches:
            # only send member if its value has changed or if allvalues is True
            if allvalues or switch.changed:
                xmldata.append(switch.oneswitch())
                switch.changed = False
                membersincluded = True
        for switch in Onswitches:
            # only send member if its value has changed or if allvalues is True
            if allvalues or switch.changed:
                xmldata.append(switch.oneswitch())
                switch.changed = False
                membersincluded = True
        if membersincluded:
            # only send xmldata if a member is included in the vector
            await self.driver.writerque.put(xmldata)


    async def send_setVectorMembers(self, message='', timestamp=None, timeout='0', members=[]):
        """Transmits the vector (setSwitchVector) and members with their values to the client.
           Similar to the send_setVector method however the members list specifies the
           member names which will have their values sent.

           This allows members to be explicitly specified. If the members list is empty
           then a vector will still be sent, empty of members, which may be required if
           just a state or message is to be sent.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        # for rule 'OneOfMany' the standard indicates 'Off' should precede 'On'
        # so make all 'On' values last
        Offswitches = (switch for switch in self.data.values() if switch.membervalue == 'Off' and switch.name in members)
        Onswitches = (switch for switch in self.data.values() if switch.membervalue == 'On' and switch.name in members)
        for switch in Offswitches:
            xmldata.append(switch.oneswitch())
            switch.changed = False
        for switch in Onswitches:
            xmldata.append(switch.oneswitch())
            switch.changed = False
        await self.driver.writerque.put(xmldata)


class LightVector(PropertyVector):

    """A LightVector is an instrument indicator, and sends one or more members
       with values 'Idle', 'Ok', 'Busy' or 'Alert'. In general a client will
       indicate this state with different colours."""

    def __init__(self, name, label, group, state, lightmembers):
        super().__init__(name, label, group, state)
        # self.data is a dictionary of light name : lightmember
        for light in lightmembers:
            if not isinstance(light, LightMember):
                raise TypeError("Members of a LightVector must all be LightMembers")
            self.data[light.name] = light

    async def _handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            # test if any xml data has been received
            try:
                root = await self.dataque.get()
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                pass
            self.dataque.task_done()

    @property
    def perm(self):
        return "ro"

    async def send_defVector(self, message='', timestamp=None, timeout='0'):
        """Transmits the vector definition (defLightVector) to the client.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which
           case a datetime.datetime.utcnow() value will be inserted.

           For Light Vectors the timeout value is not used, but is included
           in the arguments to match other send_vectors.
        """
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
        xmldata.set("state", self.state)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        for light in self.data.values():
            xmldata.append(light.deflight())
            # after a deflight sent, assume new client connection, and set all members as changed
            # so they will all be included in the first 'send_setVector'
            light.changed = True
        await self.driver.writerque.put(xmldata)


    async def send_setVector(self, message='', timestamp=None, timeout='0', allvalues=True):
        """Transmits the vector (setLightVector) and members with their values to the client.
           Typically the vector 'state' should be set, and any changed member value prior to
           transmission.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which case a
           datetime.datetime.utcnow() value will be inserted.

           For Light Vectors the timeout value is not used, but is included in the arguments
           to match other send_vectors.

           If allvalues is True, all values are sent.

           If allvalues is False, only values that have changed will be sent, saving bandwidth.
           If no values have changed, the vector will not be sent, if you need to ensure the
           vector message, state or time values are sent to the client, then use the more
           explicit send_setVectorMembers method instead.
        """
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
        # set a flag to test if at least one member is included
        membersincluded = False
        for light in self.data.values():
            # only send member if its value has changed or if allvalues is True
            if allvalues or light.changed:
                xmldata.append(light.onelight())
                light.changed = False
                membersincluded = True
        if membersincluded:
            # only send xmldata if a member is included in the vector
            await self.driver.writerque.put(xmldata)

    async def send_setVectorMembers(self, message='', timestamp=None, timeout='0', members=[]):
        """Transmits the vector (setLightVector) and members with their values to the client.
           Similar to the send_setVector method however the members list specifies the
           member names which will have their values sent.

           This allows members to be explicitly specified. If the members list is empty
           then a vector will still be sent, empty of members, which may be required if
           just a state or message is to be sent.
        """
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
        for light in self.data.values():
            if light.name in  members:
                xmldata.append(light.onelight())
                light.changed = False
        await self.driver.writerque.put(xmldata)



class TextVector(PropertyVector):

    """A TextVector is used to send and receive text between instrument and client."""

    def __init__(self, name, label, group, perm, state, textmembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        # self.data is a dictionary of text name : textmember
        for text in textmembers:
            if not isinstance(text, TextMember):
                raise TypeError("Members of a TextVector must all be TextMembers")
            self.data[text.name] = text

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    async def _handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            try:
                root = await self.dataque.get()
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
                elif root.tag == "newTextVector":
                    # create event
                    event = newTextVector(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                pass
            self.dataque.task_done()

    async def send_defVector(self, message='', timestamp=None, timeout='0'):
        """Transmits the vector definition (defTextVector) to the client.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which
           case a datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string value
           indicating to the client how long this data is valid.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        for text in self.data.values():
            xmldata.append(text.deftext())
            # after a deftext sent, assume new client connection, and set all members as changed
            # so they will all be included in the first 'send_setVector'
            text.changed = True
        await self.driver.writerque.put(xmldata)

    async def send_setVector(self, message='', timestamp=None, timeout='0', allvalues=True):
        """Transmits the vector (setTextVector) and members with their values to the client.
           Typically the vector 'state' should be set, and any changed member value prior to
           transmission.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which case a
           datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string value
           indicating to the client how long this data is valid.

           If allvalues is True, all values are sent.

           If allvalues is False, only values that have changed will be sent, saving bandwidth.
           If no values have changed, the vector will not be sent, if you need to ensure the
           vector message, state or time values are sent to the client, then use the more
           explicit send_setVectorMembers method instead.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        # set a flag to test if at least one member is included
        membersincluded = False
        for text in self.data.values():
            # only send member if its value has changed or if allvalues is True
            if allvalues or text.changed:
                xmldata.append(text.onetext())
                text.changed = False
                membersincluded = True
        if membersincluded:
            # only send xmldata if a member is included in the vector
            await self.driver.writerque.put(xmldata)

    async def send_setVectorMembers(self, message='', timestamp=None, timeout='0', members=[]):
        """Transmits the vector (setTextVector) and members with their values to the client.
           Similar to the send_setVector method however the members list specifies the
           member names which will have their values sent.

           This allows members to be explicitly specified. If the members list is empty
           then a vector will still be sent, empty of members, which may be required if
           just a state or message is to be sent.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        for text in self.data.values():
            if text.name in members:
                xmldata.append(text.onetext())
                text.changed = False
        await self.driver.writerque.put(xmldata)


class NumberVector(PropertyVector):

    def __init__(self, name, label, group, perm, state, numbermembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        # self.data is a dictionary of number name : numbermember
        for number in numbermembers:
            if not isinstance(number, NumberMember):
                raise TypeError("Members of a NumberVector must all be NumberMembers")
            self.data[number.name] = number

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    async def _handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            try:
                root = await self.dataque.get()
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
                elif root.tag == "newNumberVector":
                    # create event
                    event = newNumberVector(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                pass
            self.dataque.task_done()

    async def send_defVector(self, message='', timestamp=None, timeout='0'):
        """Transmits the vector definition (defNumberVector) to the client.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which
           case a datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string value
           indicating to the client how long this data is valid.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        for number in self.data.values():
            xmldata.append(number.defnumber())
            # after a defnumber sent, assume new client connection, and set all members as changed
            # so they will all be included in the first 'send_setVector'
            number.changed = True
        await self.driver.writerque.put(xmldata)

    async def send_setVector(self, message='', timestamp=None, timeout='0', allvalues=True):
        """Transmits the vector (setNumberVector) and members with their values to the client.
           Typically the vector 'state' should be set, and any changed member value prior to
           transmission.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which case a
           datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string value
           indicating to the client how long this data is valid.

           If allvalues is True, all values are sent.

           If allvalues is False, only values that have changed will be sent, saving bandwidth.
           If no values have changed, the vector will not be sent, if you need to ensure the
           vector message, state or time values are sent to the client, then use the more
           explicit send_setVectorMembers method instead.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        # set a flag to test if at least one member is included
        membersincluded = False
        for number in self.data.values():
            # only send member if its value has changed or if allvalues is True
            if allvalues or number.changed:
                xmldata.append(number.onenumber())
                number.changed = False
                membersincluded = True
        if membersincluded:
            # only send xmldata if a member is included in the vector
            await self.driver.writerque.put(xmldata)

    async def send_setVectorMembers(self, message='', timestamp=None, timeout='0', members=[]):
        """Transmits the vector (setNumberVector) and members with their values to the client.
           Similar to the send_setVector method however the members list specifies the
           member names which will have their values sent.

           This allows members to be explicitly specified. If the members list is empty
           then a vector will still be sent, empty of members, which may be required if
           just a state or message is to be sent.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        for number in self.data.values():
            if number.name in members:
                xmldata.append(number.onenumber())
                number.changed = False
        await self.driver.writerque.put(xmldata)


class BLOBVector(PropertyVector):

    def __init__(self, name, label, group, perm, state, blobmembers):
        super().__init__(name, label, group, state)
        self.perm = perm
        # self.data is a dictionary of blob name : blobmember
        for blob in blobmembers:
            if not isinstance(blob, BLOBMember):
                raise TypeError("Members of a BLOBVector must all be BLOBMembers")
            self.data[blob.name] = blob

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    async def _handler(self):
        """Check received data and take action"""
        while True:
            await asyncio.sleep(0)
            try:
                root = await self.dataque.get()
                if root.tag == "getProperties":
                    # create event
                    event = getProperties(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
                elif root.tag == "enableBLOB":
                    # create event
                    event = enableBLOB(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
                elif root.tag == "newBLOBVector":
                    # create event
                    event = newBLOBVector(self.devicename, self.name, self, root)
                    await self.driver.clientevent(event)
            except EventException:
                # if an error is raised parsing the incoming data, just continue
                pass
            self.dataque.task_done()

    async def send_defVector(self, message='', timestamp=None, timeout='0'):
        """Transmits the vector definition (defBLOBVector) to the client.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which
           case a datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string value
           indicating to the client how long this data is valid.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        for blob in self.data.values():
            xmldata.append(blob.defblob())
            # after a defblob sent, assume new client connection, and set all members as changed
            # so they will all be included in the first 'send_setVector'
            blob.changed = True
        await self.driver.writerque.put(xmldata)

    async def send_setVector(self, message='', timestamp=None, timeout='0', allvalues=True):
        """Transmits the vector (setBLOBVector) and members with their values to the client.
           Typically the vector 'state' should be set, and any changed member value prior to
           transmission.

           message is any suitable string for the client.

           timestamp should be a datetime.datetime object or None, in which case a
           datetime.datetime.utcnow() value will be inserted.

           The timeout value should be '0' if not used, or a string value
           indicating to the client how long this data is valid.

           If allvalues is True, all values are sent.

           If allvalues is False, only values that have changed will be sent, saving bandwidth.
           If no values have changed, the vector will not be sent, if you need to ensure the
           vector message, state or time values are sent to the client, then use the more
           explicit send_setVectorMembers method instead.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        # set a flag to test if at least one member is included
        membersincluded = False
        for blob in self.data.values():
            # only send member if its value has changed or if allvalues is True
            if allvalues or blob.changed:
                xmldata.append(blob.oneblob())
                blob.changed = False
                membersincluded = True
        if membersincluded:
            # only send xmldata if a member is included in the vector
            await self.driver.writerque.put(xmldata)

    async def send_setVectorMembers(self, message='', timestamp=None, timeout='0', members=[]):
        """Transmits the vector (setBLOBVector) and members with their values to the client.
           Similar to the send_setVector method however the members list specifies the
           member names which will have their values sent.

           This allows members to be explicitly specified. If the members list is empty
           then a vector will still be sent, empty of members, which may be required if
           just a state or message is to be sent.
        """
        if not isinstance(timeout, str):
            raise ValueError("The given timeout value must be a string object")
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
        xmldata.set("timeout", timeout)
        if message:
            xmldata.set("message", message)
        for blob in self.data.values():
            if blob.name in members:
                xmldata.append(blob.oneblob())
                blob.changed = False
        await self.driver.writerque.put(xmldata)
