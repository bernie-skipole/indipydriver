

import collections, asyncio, datetime, sys

import xml.etree.ElementTree as ET

from .comms import STDINOUT, Portcomms
from . import events


class IPyDriver(collections.UserDict):

    """A subclass of this should be created with methods written
       to control your device.

       Its awaitable asyncrun method should be run in an async loop.

       devices is a list of Device objects this driver handles.

       driverdata will be an attribute dictionary of any hardware
       data that may be usefull.
       """

    @staticmethod
    def indi_number_to_float(value):
        """The INDI spec allows a number of different number formats, given any number string, this returns a float.
           If an error occurs while parsing the number, a TypeError exception is raised."""
        try:
            if isinstance(value, float):
                return value
            if isinstance(value, int):
                return float(value)
            if not isinstance(value, str):
                raise TypeError
            # negative is True, if the value is negative
            value = value.strip()
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
        except:
            raise TypeError("Unable to parse the value")
        return floatvalue

    def __init__(self, devices, **driverdata):
        super().__init__()

        # this is a dictionary of device name to device this driver owns
        self.devices = {d.devicename:d for d in devices}

        for device in self.devices.values():
            # set driver into devices
            device.driver = self

        self.data = self.devices

        # self.data is used by UserDict, it is an alias of self.devices
        # simply because 'devices' is more descriptive

        # dictionary of optional data
        self.driverdata = driverdata

        # traffic is transmitted out on the writerque
        self.writerque = asyncio.Queue(4)
        # and read in from the readerque
        self.readerque = asyncio.Queue(4)
        # and snoop data is passed on to the snoopque
        self.snoopque = asyncio.Queue(4)
        # data for each device is passed to each device dataque

        # An object for communicating can be set, if not set, then
        # self.comms = STDINOUT() will be set in the asyncrun call
        self.comms = None

        # These set the remote traffic which this driver is snooping
        # initially the driver is not snooping anything, until it sends
        # a getProperties
        self.snoopall = False           # gets set to True if it is snooping everything
        self.snoopdevices = set()       # gets set to a set of device names
        self.snoopvectors = set()       # gets set to a set of (devicename,vectorname) tuples


    def _reporterror(self, message):
        "Prints message to stderr"
        print(message, file=sys.stderr)

    def listen(self, host="localhost", port=7624):
        """If called, listens on the given host and port. Only one connection is accepted,
           further connection attempts while a client is already connected will be refused.
           This method also checks for enableBLOB instructions, and implements them."""
        if not self.comms is None:
             raise RuntimeError("A communications method has already been set, there can only be one")
        self.comms = Portcomms(self.devices, host, port)


    async def send(self, xmldata):
        "Transmits xmldata, this is an internal method, not normally called by a user."
        if self.comms.connected:
            await self.writerque.put(xmldata)

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
            root = await self.readerque.get()
            if root.tag == "getProperties":
                version = root.get("version")
                if version != "1.7":
                    self.readerque.task_done()
                    continue
                # getProperties received with correct version
                devicename = root.get("device")
                # devicename is None (for all devices), or a named device
                if devicename is None:
                    for d in self.devices.values():
                        if d.enable:
                            await d.dataque.put(root)
                elif devicename in self.devices:
                    if self.devices[devicename].enable:
                        await self.devices[devicename].dataque.put(root)
                # else device not recognised
            elif root.tag in client_tags:
                # xml received from client
                devicename = root.get("device")
                if devicename is None:
                    # device not given, ignore this
                    self.readerque.task_done()
                    continue
                elif devicename in self.devices:
                    if self.devices[devicename].enable:
                        await self.devices[devicename].dataque.put(root)
                # else device not recognised
            elif root.tag in snoop_tags:
                # xml received from other devices
                await self.snoopque.put(root)
            self.readerque.task_done()


    async def _snoophandler(self):
        """Creates events using data from self.snoopque"""
        while True:
            # get block of data from the self.snoopque
            await asyncio.sleep(0)
            root = await self.snoopque.get()
            devicename = root.get("device")
            if devicename is not None:
                # if a device name is given, check
                # it is not in this drivers devices
                if devicename in self.devices:
                    self._reporterror("Cannot snoop on a device already controlled by this driver")
                    self.snoopque.task_done()
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
            self.snoopque.task_done()

    async def send_message(self, message="", timestamp=None):
        "Send system wide message - without device name"
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            self._reporterror("The timestamp given in send_message must be a datetime.datetime object")
            return
        xmldata = ET.Element('message')
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        await self.send(xmldata)

    async def send_getProperties(self, devicename=None, vectorname=None):
        """Sends a getProperties request - which is used to snoop data from other devices
           on the network, if devicename given, it must not be a device of this driver as
           the point of this is to snoop on remote devices."""
        xmldata = ET.Element('getProperties')
        xmldata.set("version", "1.7")
        if devicename is None:
            await self.send(xmldata)
            self.snoopall = True
            return
        if devicename in self.devices:
            self._reporterror("Cannot snoop on a device already controlled by this driver")
            return
        xmldata.set("device", devicename)
        if vectorname is None:
            await self.send(xmldata)
            self.snoopdevices.add(devicename)
            return
        xmldata.set("name", vectorname)
        await self.send(xmldata)
        # adds tuple (devicename,vectorname) to self.snoopvectors
        self.snoopvectors.add((devicename,vectorname))


    async def hardware(self):
        """Override this to operate device hardware, and transmit updates

        For example: call your own code to operate hardware
        then update the appropriate vectors, and send updated
        values to the client using
        await vector.send_setVector()"""
        await asyncio.sleep(0)


    async def clientevent(self, event):
        """Override this. On receiving data, this is called, and should
           handle any necessary actions.
           event is an object describing the event, with attributes
           devicename, vectorname, vector, root
           where vector is the properties vector the event refers to, and
           root is an xml.etree.ElementTree object of the received xml"""
        pass

    async def snoopevent(self, event):
        """Override this if this driver is snooping on other devices.
           On receiving snoop data, this is called, and should handle
           any necessary actions.
           event is an object with attributes according to the data received."""
        pass

    async def asyncrun(self):
        """Gathers tasks to be run simultaneously"""
        # set an object for communicating, as default this is stdin and stdout
        if self.comms is None:
            self.comms = STDINOUT()

        device_handlers = []
        property_handlers = []
        for device in self.devices.values():
            device_handlers.append(device._handler())
            for pv in device.propertyvectors.values():
                property_handlers.append(pv._handler())
                # also give the propertyvector a reference to this driver
                # so it can call eventaction and have access to writerque
                pv.driver = self

        await asyncio.gather(self.comms(self.readerque, self.writerque),   # run communications
                             self.hardware(),        # task to operate device hardware, and transmit updates
                             self._read_readerque(), # task to handle received xml data
                             self._snoophandler(),   # task to handle incoming snoop data
                             *device_handlers,       # each device handles its incoming data
                             *property_handlers      # each property handles its incoming data
                            )


class Device(collections.UserDict):

    """An instance of this should be created for each device controlled by this driver.
       The properties argument is a list of vectors controlling this device.
       devicedata will be an attribute dictionary of any hardware data that may be usefull.
    """

    def __init__(self, devicename, properties, **devicedata):
        super().__init__()

        # This device name
        self.devicename = devicename

        # if self.enable is False, this device ignores incoming traffic
        # and (apart from delProperty) does not transmit anything
        # from his device
        self.enable = True

        # the driver places data in this que to send data to this device
        self.dataque = asyncio.Queue(4)

        # Every property of this device has a dataque, which is set into this dictionary
        self.propertyquedict = {p.name:p.dataque for p in properties}

        # dictionary of optional data
        self.devicedata = devicedata

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

    def _reporterror(self, message):
        "Prints message to stderr"
        print(message, file=sys.stderr)

    async def send_device_message(self, message="", timestamp=None):
        """Send a message associated with this device, which the client could display.
           The timestamp should be either None or a datetime.datetime object. If the
           timestamp is None a datetime.datetime.utcnow() value will be inserted."""
        if not self.enable:
            # messages only sent if self.enable is True
            return
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            self._reporterror("The timestamp given in send_message must be a datetime.datetime object")
            return
        xmldata = ET.Element('message')
        xmldata.set("device", self.devicename)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        await self.driver.send(xmldata)

    async def send_delProperty(self, message="", timestamp=None):
        """Sending delProperty with this device method, (as opposed to the vector send_delProperty method)
           informs the client this device is not available, it also sets a device.enable attribute to
           False, which stops any data being transmitted between the client and this device.
           Setting device.enable to True re-enables communications.
           The message argument is any appropriate string which the client could display to the user.
           The timestamp should be either None or a datetime.datetime object. If the timestamp is None
           a datetime.datetime.utcnow() value will be inserted."""
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        if not isinstance(timestamp, datetime.datetime):
            self._reporterror("The timestamp given in send_delProperty must be a datetime.datetime object")
            return
        xmldata = ET.Element('delProperty')
        xmldata.set("device", self.devicename)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        if message:
            xmldata.set("message", message)
        await self.driver.send(xmldata)
        self.enable = False


    async def devhardware(self, *args, **kwargs):
        """As default, does nothing and is not called.

           If required, override this to handle any necessary device actions.
           This should be called from the driver 'hardware' method if it is used."""
        pass


    async def devclientevent(self, event, *args, **kwargs):
        """As default, does nothing and is not called.

           If required, override this to handle any necessary device actions.
           This should be called from the driver 'clientevent' method if it is used."""
        pass


    async def devsnoopevent(self, event, *args, **kwargs):
        """As default, does nothing and is not called.

           If required, override this to handle any necessary device actions.
           This should be called from the driver 'snoopevent' method if it is used."""
        pass


    def __setitem__(self, vectorname):
        raise KeyError

    async def _handler(self):
        """Handles data read from dataque"""
        while True:
            await asyncio.sleep(0)
            # get block of data from the self.dataque
            root = await self.dataque.get()

            if not self.enable:
                self.dataque.task_done()
                continue
            if root.tag == "getProperties":
                name = root.get("name")
                # name is None (for all properties), or a named property
                if name is None:
                    for pvector in self.propertyvectors.values():
                        if pvector.enable:
                            await pvector.dataque.put(root)
                elif name in self.propertyvectors:
                    if self.propertyvectors[name].enable:
                        await self.propertyvectors[name].dataque.put(root)
                else:
                    # property name not recognised
                    self.dataque.task_done()
                    continue
            elif root.tag == "enableBLOB":
                name = root.get("name")
                # name is None (for all properties), or a named property
                if name is None:
                    for pvector in self.propertyvectors.values():
                        if pvector.enable:
                            await pvector.dataque.put(root)
                elif name in self.propertyvectors:
                    if self.propertyvectors[name].enable:
                        await self.propertyvectors[name].dataque.put(root)
                else:
                    # property name not recognised
                    self.dataque.task_done()
                    continue
            else:
                # root.tag will be one of
                # newSwitchVector, newNumberVector, newTextVector, newBLOBVector
                name = root.get("name")
                if name is None:
                    # name not given, ignore this
                    self.dataque.task_done()
                    continue
                elif name in self.propertyvectors:
                    pvector = self.propertyvectors[name]
                    if pvector.perm != "ro" and pvector.enable:
                        # all ok, add to the vector dataque
                        await pvector.dataque.put(root)
            # task completed
            self.dataque.task_done()
