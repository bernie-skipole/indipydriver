

import collections

import asyncio

import datetime

import xml.etree.ElementTree as ET

from .comms import STDINOUT, Portcomms
from . import events


class IPyDriver(collections.UserDict):

    """A subclass of this should be created with methods
       clientevent and hardware written to control your device.
       Its awaitable asyncrun method should be run in an async loop.
       """

    def __init__(self, devices):
        super().__init__()

        # this is a dictionary of device name to device this driver owns
        self.devices = {d.devicename:d for d in devices}

        self.data = self.devices

        # self.data is used by UserDict, it is an alias of self.devices
        # simply because 'devices' is more descriptive

        # traffic is transmitted out on the writerque
        self.writerque = collections.deque()
        # and read in from the readerque
        self.readerque = collections.deque()
        # and snoop data is passed on to the snoopque
        self.snoopque = collections.deque()
        # data for each device is passed to each device dataque

        # set an object for communicating, as default this is stdin and stdout
        self.comms = STDINOUT()

    def listen(self, host="localhost", port=7624):
        "If called, overrides default STDINOUT and listens on the given host/port"
        self.comms = Portcomms(host, port)

    def __setitem__(self, devicename):
        raise KeyError

    async def _read_readerque(self):
        client_tags = ("enableBLOB", "newSwitchVector", "newNumberVector", "newTextVector", "newBLOBVector")
        snoop_tags = ("message", 'delProperty', 'defSwitchVector', 'setSwitchVector', 'defLightVector',
                      'setLightVector', 'defTextVector', 'setTextVector', 'defNumberVector', 'setNumberVector',
                      'defBLOBVector', 'setBLOBVector')
        while True:
            await asyncio.sleep(0)
            # reads readerque, and sends xml data to the device via its dataque
            if self.readerque:
                root = self.readerque.popleft()
                if root.tag == "getProperties":
                    version = root.get("version")
                    if version != "1.7":
                        continue
                    # getProperties received with correct version
                    devicename = root.get("device")
                    # devicename is None (for all devices), or a named device
                    if devicename is None:
                        for d in self.devices.values():
                            if d.enable:
                                d.dataque.append(root)
                    elif devicename in self.devices:
                        if self.devices[devicename].enable:
                            self.devices[devicename].dataque.append(root)
                    else:
                        # device not recognised
                        continue
                elif root.tag in client_tags:
                    # xml received from client
                    devicename = root.get("device")
                    if devicename is None:
                        # device not given, ignore this
                        continue
                    elif devicename in self.devices:
                        if self.devices[devicename].enable:
                            self.devices[devicename].dataque.append(root)
                    else:
                        # device not recognised
                        continue
                elif root.tag in snoop_tags:
                    # xml received from other devices
                    self.snoopque.append(root)


    async def _snoophandler(self):
        """Creates events using data from self.snoopque"""
        while True:
            # get block of data from the self.snoopque
            await asyncio.sleep(0)
            if self.snoopque:
                root = self.snoopque.popleft()
            else:
                continue
            devicename = root.get("device")
            if devicename is not None:
                # if a device name is given, check
                # it is not in this drivers devices
                if devicename in self.devices:
                    # cannnot snoop on self!!
                    continue
            try:
                if root.tag == "message":
                    # create event
                    event = events.message(root)
                    await self.snoopevent(event)
                elif root.tag == "delProperty":
                    # create event
                    event = events.delProperty(root)
                    await self.snoopevent(event)
                elif root.tag == "defSwitchVector":
                    # create event
                    event = events.defSwitchVector(root)
                    await self.snoopevent(event)
                elif root.tag == "setSwitchVector":
                    # create event
                    event = events.setSwitchVector(root)
                    await self.snoopevent(event)
                elif root.tag == "defLightVector":
                    # create event
                    event = events.defLightVector(root)
                    await self.snoopevent(event)
                elif root.tag == "setLightVector":
                    # create event
                    event = events.setLightVector(root)
                    await self.snoopevent(event)
                elif root.tag == "defTextVector":
                    # create event
                    event = events.defTextVector(root)
                    await self.snoopevent(event)
                elif root.tag == "setTextVector":
                    # create event
                    event = events.setTextVector(root)
                    await self.snoopevent(event)
                elif root.tag == "defNumberVector":
                    # create event
                    event = events.defNumberVector(root)
                    await self.snoopevent(event)
                elif root.tag == "setNumberVector":
                    # create event
                    event = events.setNumberVector(root)
                    await self.snoopevent(event)
                elif root.tag == "defBLOBVector":
                    # create event
                    event = events.defBLOBVector(root)
                    await self.snoopevent(event)
                elif root.tag == "setBLOBVector":
                    # create event
                    event = events.setBLOBVector(root)
                    await self.snoopevent(event)
            except events.EventException:
                # if an EventException is raised, it is because received data is malformed
                # so ignore it, and just pass
                pass


    def send_message(self, message="", timestamp=None):
        "Send system wide message - without device name"
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp given in send_message must be a datetime.datetime object")
        xmldata = ET.Element('message')
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        self.writerque.append(xmldata)

    def send_getProperties(self, devicename=None, vectorname=None):
        "sends getproperties, if devicename given, it must not be a device of this driver"
        xmldata = ET.Element('getProperties')
        if devicename is None:
            self.writerque.append(xmldata)
            return
        if devicename in self.devices:
            raise ValueError("Cannot snoop on a device already belonging to this driver")
        xmldata.set("device", devicename)
        if vectorname is None:
            self.writerque.append(xmldata)
            return
        xmldata.set("name", vectorname)
        self.writerque.append(xmldata)


    async def hardware(self):
        "Override this, operate device hardware, and transmit updates"
        await asyncio.sleep(0)
        # for example: create a number of co routines - each having
        # a while True loop, and running continuously, and controlling
        # whatever hardware is required, and calling appropriate vector
        # methods to send data, then
        # await asyncio.gather(the co routines)


    async def clientevent(self, event):
        """On receiving data, this is called, and should handle any necessary actions.
           event is an object describing the event, with attributes
           devicename, vectorname, vector,
           where vector is the properties vector causing the event."""
        pass


    async def snoopevent(self, event):
        """On receiving snoop data, this is called, and should handle any necessary actions.
           event is an object with attributes according to the event received."""
        pass


    async def asyncrun(self):
        """Gathers tasks to be run simultaneously"""

        device_handlers = []
        property_handlers = []
        for device in self.devices.values():
            # also give the device a reference to this driver
            # so it can have access to writerque
            device.driver = self
            device_handlers.append(device.handler())
            for pv in device.propertyvectors.values():
                property_handlers.append(pv.handler())
                # also give the propertyvector a reference to this driver
                # so it can call eventaction and have access to writerque
                pv.driver = self

        await asyncio.gather(self.comms.run(self.readerque, self.writerque),   # run communications
                             self.hardware(),        # task to operate device hardware, and transmit updates
                             self._read_readerque(), # task to handle received xml data
                             self._snoophandler(),   # task to handle incoming snoop data
                             *device_handlers,       # each device handles its incoming data
                             *property_handlers      # each property handles its incoming data
                            )


class Device(collections.UserDict):

    def __init__(self, devicename, properties):
        super().__init__()

        # This device name
        self.devicename = devicename

        # if self.enable is False, this device ignores incoming traffic
        # and (apart from delProperty) does not transmit anything
        # from his device
        self.enable = True

        # the driver places data in this que to send data to this device
        self.dataque = collections.deque()

        # Every property of this device has a dataque, which is set into this dictionary
        self.propertyquedict = {p.name:p.dataque for p in properties}

        # this will be set when the driver asyncrun is run
        self.driver = None

        # this is a dictionary of property name to propertyvector this device owns
        self.propertyvectors = {}
        for p in properties:
            p.devicename = self.devicename
            self.propertyvectors[p.name] = p

        self.data = self.propertyvectors
        # self.data is used by UserDict, it is an alias of self.propertyvectors
        # simply because 'propertyvectors' is more descriptive


    def send_device_message(self, message="", timestamp=None):
        "Send message associated with this device"
        if not self.enable:
            # messages only sent if self.enable is True
            return
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp given in send_message must be a datetime.datetime object")
        xmldata = ET.Element('message')
        xmldata.set("device", self.devicename)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        self.driver.writerque.append(xmldata)

    def send_message(self, message="", timestamp=None):
        "Send system wide message - without device name"
        self.driver.send_message(message, timestamp)


    def send_delProperty(self, message="", timestamp=None):
        "Send delProperty with this device, set self.enable to False"
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            raise TypeError("timestamp given in send_delProperty must be a datetime.datetime object")
        xmldata = ET.Element('delProperty')
        xmldata.set("device", self.devicename)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        self.driver.writerque.append(xmldata)
        self.enable = False

    def __setitem__(self, vectorname):
        raise KeyError


    async def handler(self):
        """Handles data read from dataque"""
        while True:
            # get block of data from the self.dataque
            await asyncio.sleep(0)
            if self.dataque:
                root = self.dataque.popleft()
                if not self.enable:
                    continue
                if root.tag == "getProperties":
                    name = root.get("name")
                    # name is None (for all properties), or a named property
                    if name is None:
                        for pvector in self.propertyvectors.values():
                            if pvector.enable:
                                pvector.dataque.append(root)
                    elif name in self.propertyvectors:
                        if self.propertyvectors[name].enable:
                            self.propertyvectors[name].dataque.append(root)
                    else:
                        # property name not recognised
                        continue
                elif root.tag == "enableBLOB":
                    name = root.get("name")
                    # name is None (for all properties), or a named property
                    if name is None:
                        for pvector in self.propertyvectors.values():
                            if pvector.enable:
                                pvector.dataque.append(root)
                    elif name in self.propertyvectors:
                        if self.propertyvectors[name].enable:
                            self.propertyvectors[name].dataque.append(root)
                    else:
                        # property name not recognised
                        continue
                else:
                    # root.tag will be either newSwitchVector, newNumberVector,.. etc
                    name = root.get("name")
                    if name is None:
                        # name not given, ignore this
                        continue
                    elif name in self.propertyvectors:
                        if self.propertyvectors[name].enable:
                            self.propertyvectors[name].dataque.append(root)
                    else:
                        # property name not recognised
                        continue


def indi_number_to_float(value):
    """The INDI spec allows a number of different number formats, given any, this returns a float"""
    # negative is True, if the value is negative
    negative = value.startswith("-")
    if negative:
        value = value.lstrip("-")
    # Is the number provided in sexagesimal form?
    if value == "":
        parts = [0, 0, 0]
    elif " " in value:
        parts = value.split(" ")
    elif ":" in value:
        parts = value.split(":")
    elif ";" in value:
        parts = value.split(";")
    else:
        # not sexagesimal
        parts = [value, "0", "0"]
    # Any missing parts should have zero
    if len(parts) == 2:
        # assume seconds are missing, set to zero
        parts.append("0")
    assert len(parts) == 3
    number_strings = list(x if x else "0" for x in parts)
    # convert strings to integers or floats
    number_list = []
    for part in number_strings:
        try:
            num = int(part)
        except ValueError:
            num = float(part)
        number_list.append(num)
    floatvalue = number_list[0] + (number_list[1]/60) + (number_list[2]/360)
    if negative:
        floatvalue = -1 * floatvalue
    return floatvalue
