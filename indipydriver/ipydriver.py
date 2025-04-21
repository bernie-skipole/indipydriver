

import collections, asyncio, sys, time, os, fcntl, logging

import xml.etree.ElementTree as ET

from . import events
from .propertyvectors import timestamp_string
from .propertymembers import getfloat


logger = logging.getLogger(__name__)


# All xml data received from the client, or from snooped devices should be contained in one of the following tags
TAGS = (b'getProperties',
        b'newTextVector',
        b'newNumberVector',
        b'newSwitchVector',
        b'newBLOBVector',
        b'enableBLOB',
        # below are tags from snooped devices
        b'message',
        b'delProperty',
        b'defSwitchVector',
        b'setSwitchVector',
        b'defLightVector',
        b'setLightVector',
        b'defTextVector',
        b'setTextVector',
        b'defNumberVector',
        b'setNumberVector',
        b'defBLOBVector',
        b'setBLOBVector'
       )


# _STARTTAGS is a tuple of ( b'<defTextVector', ...  ) data received will be tested to start with such a starttag
_STARTTAGS = tuple(b'<' + tag for tag in TAGS)


# _ENDTAGS is a tuple of ( b'</defTextVector>', ...  ) data received will be tested to end with such an endtag
_ENDTAGS = tuple(b'</' + tag + b'>' for tag in TAGS)


def _makestart(element):
    "Given an xml element, returns a string of its start, including < tag attributes >"
    attriblist = ["<", element.tag]
    for key,value in element.attrib.items():
        attriblist.append(f" {key}=\"{value}\"")
    attriblist.append(">")
    return "".join(attriblist)


class IPyDriver(collections.UserDict):

    """A subclass of this should be created with methods written
       to control your device.

       devices are Device objects this driver handles.

       You may optionally include named arguments of any instrumentation
       objects that may be useful to you, these will be available in
       the dictionary self.driverdata.

       This object is also a mapping, of devicename:deviceobject
       """

    @staticmethod
    def indi_number_to_float(value):
        """The INDI spec allows a number of different number formats, given any number string, this returns a float.
           If an error occurs while parsing the number, a TypeError exception is raised."""
        return getfloat(value)


    def __init__(self, *devices, **driverdata):
        super().__init__()

        # self.data is defined as empty dictionary in UserDict
        for device in devices:
            devicename = device.devicename
            if devicename in self.data:
                # duplicate devicename
                raise ValueError(f"Device name {devicename} is duplicated in this driver.")
            self.data[devicename] = device
            # set driver into devices
            device.driver = self

        # self.data is used by UserDict, it will become
        # a dictionary of {devicename:device, ... }

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
        # self.comms = _STDINOUT() will be set in the asyncrun call
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

        self.debug_enable = False
        # If True, xmldata will be logged at DEBUG level

        self.auto_send_def = True
        # If True, whenever a getProperties event is received, a
        # vector send_defVector() will be called, automatically replying with
        # the vector definition.
        # If set to False, the driver developer will need to implement a send_defVector()
        # in the rxevent method

        self._stop = False
        # shutdown routine sets this to True to stop coroutines

        self.stopped = asyncio.Event()
        # this is set when asyncrun is finished


    def devices(self):
        "Returns a list of device objects"
        return list(self.data.values())

    def shutdown(self):
        "Shuts down the driver, sets the flag self.stop to True"
        self._stop = True
        if self.comms is not None:
            self.comms.shutdown()
        for device in self.data.values():
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
            try:
                root = await asyncio.wait_for(self.readerque.get(), 0.5)
            except asyncio.TimeoutError:
                continue
            self.readerque.task_done()
            # log the received data
            if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
                binarydata = ET.tostring(root)
                logger.debug(f"RX:: {binarydata.decode('utf-8')}")
            if root.tag == "getProperties":
                version = root.get("version")
                if version != "1.7":
                    continue
                # getProperties received with correct version
                devicename = root.get("device")
                # devicename is None (for all devices), or a named device
                if devicename is None:
                    for d in self.data.values():
                        if d.enable:
                            await self._queueput(d.dataque, root)
                elif devicename in self.data:
                    if self.data[devicename].enable:
                        await self._queueput(self.data[devicename].dataque, root)
                # else device not recognised
            elif root.tag in client_tags:
                # xml received from client
                devicename = root.get("device")
                if devicename is None:
                    # device not given, ignore this
                    continue
                elif devicename in self.data:
                    if self.data[devicename].enable:
                        await self._queueput(self.data[devicename].dataque, root)
                # else device not recognised
            elif root.tag in snoop_tags:
                # xml received from other devices
                await self._queueput(self.snoopque, root)


    async def _call_snoopevent(self, event):
        "Update timestamp when snoop data received and call self.snoopevent"
        if event.devicename and event.vectorname:
            # update timestamp in self.snoopvectors
            timedata = self.snoopvectors.get((event.devicename, event.vectorname))
            if timedata is not None:
                timedata[1] = time.time()
        await self.snoopevent(event)


    async def _snoophandler(self):
        """Creates events using data from self.snoopque"""
        while not self._stop:
            # get block of data from the self.snoopque
            try:
                root = await asyncio.wait_for(self.snoopque.get(), 0.5)
            except asyncio.TimeoutError:
                continue
            self.snoopque.task_done()
            devicename = root.get("device")
            if devicename is not None:
                # if a device name is given, check
                # it is not in this drivers devices
                if devicename in self.data:
                    logger.error("Cannot snoop on a device already controlled by this driver")
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
            except events.EventException:
                # if an EventException is raised, it is because received data is malformed
                # so log it
                logger.exception("An exception occurred creating a snoop event")


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
        if devicename in self.data:
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
        if devicename in self.data:
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
        """This is an internal method called whenever a getProperties
           event is received from the client. It replies with a send_defVector
           to send a property vector definition back to the client.
           It would normally never be called by users own code.
           If the auto_send_def attribute is False, this does not send anything,
           and the getProperties event needs to be handled by rxevent."""
        if self.auto_send_def:
            await event.vector.send_defVector()
        else:
            await self.rxevent(event)

    async def asyncrun(self):
        """await this to operate the driver, which will then communicate by
           stdin and stdout.

           Do not await this if the driver is being set into IPyServer, in
           that situation the IPyServer will control communications."""

        logger.info(f"Driver {self.__class__.__name__} started")
        self._stop = False

        # set an object for communicating, as default this is stdin and stdout
        if self.comms is None:
            self.comms = _STDINOUT()

        # get all tasks into a list

        tasks = [ self.comms(self.readerque, self.writerque),    # run communications
                  self.hardware(),                               # task to operate device hardware, and transmit updates
                  self._read_readerque(),                        # task to handle received xml data
                  self._monitorsnoop(),                          # task to monitor if a getproperties needs to be sent
                  self._snoophandler() ]                         # task to handle incoming snoop data

        for device in self.data.values():
            tasks.append(device._handler())                           # each device handles its incoming data
            for pv in device.values():
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

       This object will be a mapping of vector name to vector object
    """

    def __init__(self, devicename, properties, **devicedata):
        super().__init__()

        if not devicename.isascii():
            raise ValueError("Device name should be all ascii characters.")

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

        # self.data is a dictionary of name to vector this device owns
        for p in properties:
            p.devicename = self.devicename
            self.data[p.name] = p

        # shutdown routine sets this to True to stop coroutines
        self._stop = False


    def properties(self):
        "Returns a list of vector objects"
        return list(self.data.values())


    def shutdown(self):
        """Shuts down the device, sets the flag self._stop to True
           and shuts down property vector handlers"""
        self._stop = True
        for pv in self.data.values():
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
            try:
                root = await asyncio.wait_for(self.dataque.get(), 0.5)
            except asyncio.TimeoutError:
                continue
            self.dataque.task_done()
            if not self.enable:
                continue
            if root.tag == "getProperties":
                name = root.get("name")
                # name is None (for all properties), or a named property
                if name is None:
                    for pvector in self.data.values():
                        if pvector.enable:
                            await self._queueput(pvector.dataque, root)
                elif name in self.data:
                    if self.data[name].enable:
                        await self._queueput(self.data[name].dataque, root)
                else:
                    # property name not recognised
                    continue
            elif root.tag == "enableBLOB":
                name = root.get("name")
                # name is None (for all properties), or a named property
                if name is None:
                    for pvector in self.data.values():
                        if pvector.enable:
                            await self._queueput(pvector.dataque, root)
                elif name in self.data:
                    if self.data[name].enable:
                        await self._queueput(self.data[name].dataque, root)
                else:
                    # property name not recognised
                    continue
            else:
                # root.tag will be one of
                # newSwitchVector, newNumberVector, newTextVector, newBLOBVector
                name = root.get("name")
                if name is None:
                    # name not given, ignore this
                    continue
                elif name in self.data:
                    pvector = self.data[name]
                    if pvector.perm != "ro" and pvector.enable:
                        # all ok, add to the vector dataque
                        await self._queueput(pvector.dataque, root)


class _STDOUT_TX:
    "An object that transmits data on stdout, used by _STDINOUT as one half of the communications path"

    def __init__(self):
        self._stop = False       # Gets set to True to stop communications

    def shutdown(self):
        self._stop = True

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop


    async def run_tx(self, writerque):
        """Gets data from writerque, and transmits it out on stdout"""
        while not self._stop:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit down stdout
            try:
                txdata = await asyncio.wait_for(writerque.get(), 0.5)
            except asyncio.TimeoutError:
                # test self._stop again
                continue
            writerque.task_done()
            if txdata is None:
                await asyncio.sleep(0.02)
                continue
            if (txdata.tag == "setBLOBVector") and len(txdata):
                # txdata is a setBLOBVector containing blobs
                # send initial setBLOBVector
                startdata = _makestart(txdata)
                sys.stdout.buffer.write(startdata.encode())
                sys.stdout.buffer.flush()
                for oneblob in txdata.iter('oneBLOB'):
                    bytescontent = oneblob.text.encode()
                    # send start of oneblob
                    startoneblob = _makestart(oneblob)
                    sys.stdout.buffer.write(startoneblob.encode())
                    sys.stdout.buffer.flush()
                    # send content in chunks
                    chunksize = 1000
                    for b in range(0, len(bytescontent), chunksize):
                        byteschunk = bytescontent[b:b+chunksize]
                        sys.stdout.buffer.write(byteschunk)
                        sys.stdout.buffer.flush()
                        await asyncio.sleep(0)
                    sys.stdout.buffer.write(b"</oneBLOB>")
                    sys.stdout.buffer.flush()
                # send enddata
                sys.stdout.buffer.write(b"</setBLOBVector>\n")
                sys.stdout.buffer.flush()
            else:
                # its straight xml, send it out on stdout
                binarydata = ET.tostring(txdata)
                binarydata += b"\n"
                sys.stdout.buffer.write(binarydata)
                sys.stdout.buffer.flush()


class _STDIN_RX:
    """An object that receives data on stdin, parses it to ElementTree elements
       and passes it to the driver by appending it to the driver's readerque"""

    def __init__(self):
        self._remainder = b""    # Used to store intermediate data
        self._stop = False       # Gets set to True to stop communications

    def shutdown(self):
        self._stop = True

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop

    async def run_rx(self, readerque):
        "pass data to readerque"
        try:
            # get block of xml.etree.ElementTree data
            # from self._xmlinput and append it to readerque
            while not self._stop:
                rxdata = await self._xmlinput()
                if rxdata is None:
                    return
                # append it to readerque
                while not self._stop:
                    try:
                        await asyncio.wait_for(readerque.put(rxdata), timeout=0.5)
                    except asyncio.TimeoutError:
                        # queue is full, continue while loop, checking stop flag
                        continue
                    # rxdata is now in readerque, break the inner while loop
                    break
        except Exception:
            logger.exception("Exception report from _STDIN_RX.run_rx")
            raise

    async def _xmlinput(self):
        """get data from  _datainput, parse it, and return it as xml.etree.ElementTree object
           Returns None if stop flags arises"""
        message = b''
        messagetagnumber = None
        while not self._stop:
            await asyncio.sleep(0)
            data = await self._datainput()
            # data is either None, or binary data ending in b">"
            if data is None:
                return
            if self._stop:
                return
            if not message:
                # data is expected to start with <tag, first strip any newlines
                data = data.strip()
                for index, st in enumerate(_STARTTAGS):
                    if data.startswith(st):
                        messagetagnumber = index
                        break
                    elif st in data:
                        # remove any data prior to a starttag
                        positionofst = data.index(st)
                        data = data[positionofst:]
                        messagetagnumber = index
                        break
                else:
                    # data does not start with a recognised tag, so ignore it
                    # and continue waiting for a valid message start
                    continue
                # set this data into the received message
                message = data
                # either further children of this tag are coming, or maybe its a single tag ending in "/>"
                if message.endswith(b'/>'):
                    # the message is complete, handle message here
                    try:
                        root = ET.fromstring(message.decode("us-ascii"))
                    except Exception:
                        # failed to parse the message, continue at beginning
                        message = b''
                        messagetagnumber = None
                        continue
                    # xml datablock done, return it
                    return root
                # and read either the next message, or the children of this tag
                continue
            # To reach this point, the message is in progress, with a messagetagnumber set
            # keep adding the received data to message, until an endtag is reached
            message += data
            if message.endswith(_ENDTAGS[messagetagnumber]):
                # the message is complete, handle message here
                try:
                    root = ET.fromstring(message.decode("us-ascii"))
                except Exception:
                    # failed to parse the message, continue at beginning
                    message = b''
                    messagetagnumber = None
                    continue
                # xml datablock done, return it
                return root
            # so message is in progress, with a messagetagnumber set
            # but no valid endtag received yet, so continue the loop


    async def _datainput(self):
        """Waits for binary string of data ending in > from stdin
           Returns None if stop flags arises"""
        remainder = self._remainder
        if b">" in remainder:
            # This returns with binary data ending in > as long
            # as there are > characters in self._remainder
            binarydata, self._remainder = remainder.split(b'>', maxsplit=1)
            binarydata += b">"
            return binarydata
        # As soon as there are no > characters left in self._remainder
        # get more data from stdin
        while not self._stop:
            await asyncio.sleep(0)
            indata = sys.stdin.buffer.read(100)
            if not indata:
                await asyncio.sleep(0.02)
                continue
            remainder += indata
            if b">" in indata:
                binarydata, self._remainder = remainder.split(b'>', maxsplit=1)
                binarydata += b">"
                return binarydata



class _STDINOUT():
    """If indipydriver.comms is set to an instance of this class it is
       used to implement communications via stdin and stdout"""

    def __init__(self):
        self.connected = True
        self.rx = _STDIN_RX()
        self.tx = _STDOUT_TX()
        self._stop = False       # Gets set to True to stop communications


    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop

    def shutdown(self):
        self._stop = True
        self.rx.shutdown()
        self.tx.shutdown()

    async def __call__(self, readerque, writerque):
        "Called from indipydriver.asyncrun() to run the communications"
        # Set stdin to non-blocking mode
        flags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)

        logger.info("Communicating via STDIN/STDOUT")

        await asyncio.gather(self.rx.run_rx(readerque),
                             self.tx.run_tx(writerque)
                             )
