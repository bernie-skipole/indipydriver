

import collections, asyncio, sys, copy, time

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

import logging
logger = logging.getLogger(__name__)

from .comms import STDINOUT, Portcomms, queueget
from . import events
from .propertyvectors import timestamp_string


class IPyDriver(collections.UserDict):

    """A subclass of this should be created with methods written
       to control your device.

       devices are Device objects this driver handles.

       You may optionally include named arguments of any hardware
       data that may be usefull to you, these will be available as
       attribute dictionary self.driverdata.

       This object is also a mapping, of devicename:deviceobject
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
                parts = ["0", "0", "0"]
            elif " " in value:
                parts = value.split(" ")
            elif ":" in value:
                parts = value.split(":")
            elif ";" in value:
                parts = value.split(";")
            else:
                # not sexagesimal
                parts = [value, "0", "0"]
            if len(parts) > 3:
                raise TypeError
            # Any missing parts should have zero
            if len(parts) == 1:
                parts.append("0")
                parts.append("0")
            if len(parts) == 2:
                parts.append("0")
            assert len(parts) == 3
            # a part could be empty string, ie if 2:5: is given
            numbers = list(float(x) if x else 0.0 for x in parts)
            floatvalue = numbers[0] + (numbers[1]/60) + (numbers[2]/3600)
            if negative:
                floatvalue = -1 * floatvalue
        except Exception:
            raise TypeError("Error: Unable to parse number value")
        return floatvalue


    def __init__(self, *devices, **driverdata):
        super().__init__()

        self.devices = {}
        for device in devices:
            devicename = device.devicename
            if devicename in self.devices:
                # duplicate devicename
                raise ValueError(f"Device name {devicename} is duplicated in this driver.")
            self.devices[devicename] = device
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

        self.snoopvectors = {}
        # The keys of self.snoopvectors will be tuples (devicename,vectorname)
        # of vectors that are to be snooped
        # The values will be either None or lists of [timeout, timestamp]

        # timeout is integer seconds set by the snoop() method
        # timestamp is updated whenever snoop data from devicename,vectorname
        # is received.
        # The coroutine _monitorsnoop Checks if current time is greater than
        # timeout+timestamp, and if it is, sends a getproperties

        # If True, xmldata will be logged at DEBUG level
        self.debug_enable = False

        # shutdown routine sets this to True to stop coroutines
        self._stop = False
        # this is set when asyncrun is finished
        self.stopped = asyncio.Event()

    def shutdown(self):
        "Shuts down the driver, sets the flag self.stop to True"
        self._stop = True
        if not self.comms is None:
            self.comms.shutdown()
        for device in self.devices.values():
            device.shutdown()

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop


    async def _queueput(self, queue, value, timeout=0.5):
        while not self._stop:
            try:
                await asyncio.wait_for(queue.put(value), timeout)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            break

    def listen(self, host="localhost", port=7624):
        """If called, sets up listening on the given host and port.
           Only one connection will accepted, further connection attempts
           while a client is already connected will be refused.
           This method also checks for enableBLOB instructions, and implements them.
           In general, using IPyServer is preferred."""
        if not self.comms is None:
             raise RuntimeError("A communications method has already been set, there can only be one")
        self.comms = Portcomms(self.devices, host, port)


    async def send(self, xmldata):
        "Transmits xmldata, this is an internal method, not normally called by a user."
        if not self.comms.connected:
            return
        while not self._stop:
            if not self.comms.connected:
                return
            try:
                await asyncio.wait_for(self.writerque.put(xmldata), timeout=0.5)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            break
        if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
            if (xmldata.tag == "setBLOBVector") and len(xmldata):
                data = copy.deepcopy(xmldata)
                for element in data:
                    element.text = "NOT LOGGED"
                binarydata = ET.tostring(data)
                logger.debug(f"TX:: {binarydata.decode('utf-8')}")
            else:
                binarydata = ET.tostring(xmldata)
                logger.debug(f"TX:: {binarydata.decode('utf-8')}")


    def __setitem__(self, devicename):
        raise KeyError

    async def _read_readerque(self):
        client_tags = ("enableBLOB", "newSwitchVector", "newNumberVector", "newTextVector", "newBLOBVector")
        snoop_tags = ("message", 'delProperty', 'defSwitchVector', 'setSwitchVector', 'defLightVector',
                      'setLightVector', 'defTextVector', 'setTextVector', 'defNumberVector', 'setNumberVector',
                      'defBLOBVector', 'setBLOBVector')
        while not self._stop:
            # reads readerque, and sends xml data to the device via its dataque
            quexit, root = await queueget(self.readerque)
            if quexit:
                continue
            # log the received data
            if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
                if ((root.tag == "setBLOBVector") or (root.tag == "newBLOBVector")) and len(root):
                    data = copy.deepcopy(root)
                    for element in data:
                        element.text = "NOT LOGGED"
                    binarydata = ET.tostring(data)
                    logger.debug(f"RX:: {binarydata.decode('utf-8')}")
                else:
                    binarydata = ET.tostring(root)
                    logger.debug(f"RX:: {binarydata.decode('utf-8')}")
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
                            await self._queueput(d.dataque, root)
                elif devicename in self.devices:
                    if self.devices[devicename].enable:
                        await self._queueput(self.devices[devicename].dataque, root)
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
                        await self._queueput(self.devices[devicename].dataque, root)
                # else device not recognised
            elif root.tag in snoop_tags:
                # xml received from other devices
                await self._queueput(self.snoopque, root)
            self.readerque.task_done()

    async def _call_snoopevent(self, event):
        "Update timestamp when snoop data received and call self.snoopevent"
        if event.devicename and event.vectorname:
            # update timestamp in self.snoopvectors
            timedata = self.snoopvectors.get((event.devicename, event.vectorname))
            if not timedata is None:
                timedata[1] = time.time()
        await self.snoopevent(event)


    async def _snoophandler(self):
        """Creates events using data from self.snoopque"""
        while not self._stop:
            # get block of data from the self.snoopque
            quexit, root = await queueget(self.snoopque)
            if quexit:
                continue
            devicename = root.get("device")
            if devicename is not None:
                # if a device name is given, check
                # it is not in this drivers devices
                if devicename in self.devices:
                    logger.error("Cannot snoop on a device already controlled by this driver")
                    self.snoopque.task_done()
                    continue
            try:
                if root.tag == "message":
                    # create event
                    event = events.message(root)
                    await self._call_snoopevent(event)
                elif root.tag == "delProperty":
                    # create event
                    event = events.delProperty(root)
                    await self._call_snoopevent(event)
                elif root.tag == "defSwitchVector":
                    # create event
                    event = events.defSwitchVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "setSwitchVector":
                    # create event
                    event = events.setSwitchVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "defLightVector":
                    # create event
                    event = events.defLightVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "setLightVector":
                    # create event
                    event = events.setLightVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "defTextVector":
                    # create event
                    event = events.defTextVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "setTextVector":
                    # create event
                    event = events.setTextVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "defNumberVector":
                    # create event
                    event = events.defNumberVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "setNumberVector":
                    # create event
                    event = events.setNumberVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "defBLOBVector":
                    # create event
                    event = events.defBLOBVector(root)
                    await self._call_snoopevent(event)
                elif root.tag == "setBLOBVector":
                    # create event
                    event = events.setBLOBVector(root)
                    await self._call_snoopevent(event)
            except events.EventException as ex:
                # if an EventException is raised, it is because received data is malformed
                # so log it
                logger.exception("An exception occurred creating a snoop event")
            self.snoopque.task_done()

    async def send_message(self, message="", timestamp=None):
        "Send system wide message - without device name"
        tstring = timestamp_string(timestamp)
        if not tstring:
            logger.error("The timestamp given in send_message must be a datetime.datetime UTC object")
            return
        xmldata = ET.Element('message')
        xmldata.set("timestamp", tstring)
        if message:
            xmldata.set("message", message)
        await self.send(xmldata)


    def snoop(self, devicename, vectorname, timeout=30):
        """Call this to snoop on a given devicename, vectorname.
           This will cause a getProperties to be sent, and will also
           send further getProperties every timeout seconds if no snooping
           data is being received from the specified vector.
           This avoids a possible problem where intermediate servers may
           be temporarily turned off, and will lose their instruction to
           broadcast snooping traffic. This method is only applicable when
           snooping on a specific device vector.
           timeout must be an integer equal or greater than 5 seconds."""
        if devicename in self.devices:
            logger.error("Cannot snoop on a device already controlled by this driver")
            return
        timeout = int(timeout)
        if timeout < 5:
            logger.error("Snoop timout should be equal or greater than 5 seconds")
            return

        current = time.time()

        # set self.snoopvectors[(devicename,vectorname)] to [timeout, timestamp]

        self.snoopvectors[(devicename,vectorname)] = [timeout, current - timeout + 1]

        # setting timestamp to current - timeout + 1 means that after a second
        # the coroutine _monitorsnoop will think that its own time measurement
        # is greater than the timestamp plus timeout and will send a send_getProperties


    async def _monitorsnoop(self):
        "Checks if any snooping vectors have timed out, if it has, sends getproperties"
        while not self._stop:
            await asyncio.sleep(1)
            if not self.snoopvectors:
                continue
            current = time.time()
            for key, value in self.snoopvectors.items():
                if value is None:
                    continue
                timeout, timestamp = value
                if current > timestamp + timeout:
                    # the timeout has expired, update timestamp and send getproperties
                    value[1] = current
                    await self.send_getProperties(*key)


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
            logger.error("Cannot snoop on a device already controlled by this driver")
            return
        xmldata.set("device", devicename)
        if vectorname is None:
            await self.send(xmldata)
            self.snoopdevices.add(devicename)
            return
        xmldata.set("name", vectorname)
        await self.send(xmldata)
        # adds tuple (devicename,vectorname) to self.snoopvectors
        if (devicename,vectorname) not in self.snoopvectors:
            self.snoopvectors[(devicename,vectorname)] = None


    async def hardware(self):
        """Override this to operate device hardware, and transmit updates

        For example: call your own code to operate hardware
        then update the appropriate vectors, and send updated
        values to the client using
        await vector.send_setVector()"""
        pass


    async def rxevent(self, event):
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


    async def rxgetproperties(self, event):
        """This is an internal method called wherever a getProperties
           event is received from the client. It replies with a send_defVector
           to send a property vector definition back to the client.
           It would normally never be called by users own code"""
        await event.vector.send_defVector()

    async def asyncrun(self):
        """await this to operate the driver, which will then communicate by
           stdin and stdout, unless the listen method is called first, in
           which case it will listen via the specified port.

           Do not await this if the driver is being set into IPyServer, in
           that situation the IPyServer will control communications."""

        logger.info(f"Driver {self.__class__.__name__} started")
        self._stop = False

        # set an object for communicating, as default this is stdin and stdout
        if self.comms is None:
            self.comms = STDINOUT()

        # get all tasks into a list

        tasks = [ self.comms(self.readerque, self.writerque),    # run communications
                  self.hardware(),                               # task to operate device hardware, and transmit updates
                  self._read_readerque(),                        # task to handle received xml data
                  self._monitorsnoop(),                          # task to monitor if a getproperties needs to be sent
                  self._snoophandler() ]                         # task to handle incoming snoop data

        for device in self.devices.values():
            tasks.append(device._handler())                           # each device handles its incoming data
            for pv in device.propertyvectors.values():
                tasks.append(pv._handler())                           # each property handles its incoming data
                # also give the propertyvector a reference to this driver
                # so it can call eventaction and have access to writerque
                pv.driver = self
        try:
            await asyncio.gather( *tasks )
        finally:
            self.stopped.set()
            self._stop = True

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

       # shutdown routine sets this to True to stop coroutines
        self._stop = False

    def shutdown(self):
        """Shuts down the device, sets the flag self._stop to True
           and shuts down property vector handlers"""
        self._stop = True
        for pv in self.propertyvectors.values():
            pv.shutdown()

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop


    async def _queueput(self, queue, value, timeout=0.5):
        while not self._stop:
            try:
                await asyncio.wait_for(queue.put(value), timeout)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            break

    async def send_device_message(self, message="", timestamp=None):
        """Send a message associated with this device, which the client could display.
           The timestamp should be either None or a datetime.datetime object. If the
           timestamp is None a UTC value will be inserted."""
        if not self.enable:
            # messages only sent if self.enable is True
            return
        tstring = timestamp_string(timestamp)
        if not tstring:
            logger.error("The timestamp given in send_device_message must be a datetime.datetime UTC object")
            return
        xmldata = ET.Element('message')
        xmldata.set("device", self.devicename)
        xmldata.set("timestamp", tstring)
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
           a UTC value will be inserted."""
        tstring = timestamp_string(timestamp)
        if not tstring:
            logger.error("The timestamp given in send_delProperty must be a datetime.datetime UTC object")
            return
        xmldata = ET.Element('delProperty')
        xmldata.set("device", self.devicename)
        xmldata.set("timestamp", tstring)
        if message:
            xmldata.set("message", message)
        await self.driver.send(xmldata)
        self.enable = False


    async def devhardware(self, *args, **kwargs):
        """As default, does nothing and is not called.

           If required, override this to handle any necessary device actions.
           This should be called from the driver 'hardware' method if it is used."""
        pass


    async def devrxevent(self, event, *args, **kwargs):
        """As default, does nothing and is not called.

           If required, override this to handle any necessary device actions.
           This should be called from the driver 'rxevent' method if it is used."""
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
        while not self._stop:
            # get block of data from the self.dataque
            quexit, root = await queueget(self.dataque)
            if quexit:
                continue
            if not self.enable:
                self.dataque.task_done()
                continue
            if root.tag == "getProperties":
                name = root.get("name")
                # name is None (for all properties), or a named property
                if name is None:
                    for pvector in self.propertyvectors.values():
                        if pvector.enable:
                            await self._queueput(pvector.dataque, root)
                elif name in self.propertyvectors:
                    if self.propertyvectors[name].enable:
                        await self._queueput(self.propertyvectors[name].dataque, root)
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
                            await self._queueput(pvector.dataque, root)
                elif name in self.propertyvectors:
                    if self.propertyvectors[name].enable:
                        await self._queueput(self.propertyvectors[name].dataque, root)
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
                        await self._queueput(pvector.dataque, root)
            # task completed
            self.dataque.task_done()
