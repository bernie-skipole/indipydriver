

import os, sys, collections, asyncio, time, copy, json

from time import sleep

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

import logging
logger = logging.getLogger(__name__)

from . import events

from .propertymembers import ParseException


# All xml data received from the driver should be contained in one of the following tags
TAGS = (b'message',
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
        b'setBLOBVector',
        b'getProperties'       # for snooping
       )

DEFTAGS = ( 'defSwitchVector',
            'defLightVector',
            'defTextVector',
            'defNumberVector',
            'defBLOBVector'
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



class IPyClient(collections.UserDict):

    """This class can be used to create your own scripts or client, and provides
       a connection to an INDI service, with parsing of the XML protocol.
       You should create your own class, inheriting from this, and overriding the
       rxevent method.
       The argument clientdata provides any named arguments you may wish to pass
       into the object when instantiating it.
       The IPyClient object is also a mapping of devicename to device object, which
       is populated as devices and their vectors are learned from the INDI protocol."""


    def __init__(self, indihost="localhost", indiport=7624, **clientdata):
        "An instance of this is a mapping of devicename to device object"
        super().__init__()

        # The UserDict will create self.data which will become
        # a dictionary of devicename to device object

        self.indihost = indihost
        self.indiport = indiport

        # dictionary of optional data
        self.clientdata = clientdata

        # create queue where client will put xml data to be transmitted
        self._writerque = asyncio.Queue(4)

        # and create readerque where received xmldata will be put
        self._readerque = asyncio.Queue(4)

        # self.messages is a deque of (Timestamp, message) tuples
        self.messages = collections.deque(maxlen=8)

        # note, messages are added with 'appendleft'
        # so newest message is messages[0]
        # oldest message is messages[-1] or can be obtained with .pop()

        # self.connected is True if connection has been made
        self.connected = False

        #####################
        # The following sets of timers are only enabled if this is True
        self.timeout_enable = True

        # vector timeouts are used to check that when a new vector is sent
        # a reply setvector will be received within the given time
        self.vector_timeout_min = 2
        self.vector_timeout_max = 10

        # idle_timer is set when either data is transmitted or received.
        # If nothing is sent or received after idle_timeout reached, then a getProperties is transmitted
        self.idle_timer = time.time()
        self.idle_timeout = 20
        # self.idle_timeout is set to two times self.vector_timeout_max

        # tx_timer is set when any data is transmitted,
        # it is used to check when any data is received,
        # at which point it becomes None again.
        # if there is no answer after self.respond_timeout seconds,
        # assume the connection has failed and close the connection
        self.tx_timer = None
        self.respond_timeout = 40
        # self.respond_timeout is set to four times self.vector_timeout_max
        ######################

        # and shutdown routine sets this to True to stop coroutines
        self._stop = False
        # this is set when asyncrun is finished
        self.stopped = asyncio.Event()

        # Indicates how verbose the debug xml logs will be when created.
        self._verbose = 1

        # Enables reports, by adding INFO logs to client messages
        self.enable_reports = True


    def debug_verbosity(self, verbose):
        """Set how verbose the debug xml logs will be when created.

           |  0 no xml logs will be generated
           |  1 for transmitted/received vector tags only,
           |  2 for transmitted/received vectors, members and contents (apart from BLOBs)
           |  3 for all transmitted/received data including BLOBs."""
        if verbose not in (0,1,2,3):
            raise ValueError
        self._verbose = verbose

    async def hardware(self):
        """This is started when asyncrun is called. As default does nothing so stops immediately.
           It is available to be overriden if required."""
        pass

    def shutdown(self):
        "Shuts down the client, sets the flag self._stop to True"
        self._stop = True

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the client"
        return self._stop


    async def queueput(self, queue, value, timeout=0.5):
        """Given an asyncio.Queue object, if self.stop is not set, this
           attempts to put value into the queue.
           If the queue is full, and the put operation is waiting, then
           after the timeout period the check and put will be repeated
           until successful, or self.stop becomes True.
           Returns True if value added to queue.
           Returns False if stop is True and the value not added."""
        while not self._stop:
            try:
                await asyncio.wait_for(queue.put(value), timeout)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            return True
        return False


    async def report(self, message):
        """If logging is enabled message will be logged at level INFO.
           If self.enable_reports is True, the message will be injected into
           the received data, which will be picked up by the rxevent method.
           It is a way to set a message on to your client display, in the
           same way messages come from the INDI service."""
        try:
            logger.info(message)
            if not self.enable_reports:
                return
            timestamp = datetime.now(tz=timezone.utc)
            timestamp = timestamp.replace(tzinfo=None)
            root = ET.fromstring(f"<message timestamp=\"{timestamp.isoformat(sep='T')}\" message=\"{message}\" />")
            # and place root into readerque
            await self.queueput(self._readerque, root)
        except Exception :
            logger.exception("Exception report from IPyClient.report method")


    def enabledlen(self):
        "Returns the number of enabled devices"
        return sum(map(lambda x:1 if x.enable else 0, self.data.values()))


    def __setitem__(self, device):
        "Devices are added by being learnt from the driver, they cannot be manually added"
        raise KeyError


    async def _comms(self):
        "Create a connection to an INDI port"
        try:
            while not self._stop:
                self.tx_timer = None
                self.idle_timer = time.time()
                t1 = None
                t2 = None
                t3 = None
                try:
                    # start by openning a connection
                    await self.report(f"Attempting to connect to {self.indihost}:{self.indiport}")
                    reader, writer = await asyncio.open_connection(self.indihost, self.indiport)
                    self.connected = True
                    self.messages.clear()
                    # clear devices etc
                    self.clear()
                    await self.report(f"Connected to {self.indihost}:{self.indiport}")
                    t1 = asyncio.create_task(self._run_tx(writer))
                    t2 = asyncio.create_task(self._run_rx(reader))
                    t3 = asyncio.create_task(self._check_alive(writer))
                    await asyncio.gather(t1, t2, t3)
                except ConnectionRefusedError:
                    await self.report(f"Connection refused on {self.indihost}:{self.indiport}")
                except ConnectionError:
                    await self.report(f"Connection Lost on {self.indihost}:{self.indiport}")
                except Exception:
                    logger.exception(f"Connection Error on {self.indihost}:{self.indiport}")
                    await self.report("Connection failed")
                self._clear_connection()
                # connection has failed, ensure all tasks are done
                if t1:
                    while not t1.done():
                        await asyncio.sleep(0)
                if t2:
                    while not t2.done():
                        await asyncio.sleep(0)
                if t3:
                    while not t3.done():
                        await asyncio.sleep(0)
                if self._stop:
                    break
                else:
                    await self.report(f"Connection failed, re-trying...")
                # wait five seconds before re-trying, but keep checking
                # that self._stop has not been set
                count = 0
                while not self._stop:
                    await asyncio.sleep(0.5)
                    count += 1
                    if count >= 10:
                        break
        except Exception:
            logger.exception("Exception report from IPyClient._comms method")
            raise
        finally:
            self.shutdown()


    def _clear_connection(self):
        "On a connection closing down, self.connected is set to False"
        self.connected = False
        self.tx_timer = None



    async def send(self, xmldata):
        """Transmits xmldata, this is an internal method, not normally called by a user.
           xmldata is an xml.etree.ElementTree object"""
        if self.connected and (not self._stop):
            await self.queueput(self._writerque, xmldata)


    async def _check_alive(self, writer):
        try:
            while self.connected and (not self._stop):
                await asyncio.sleep(0.1)
                if self.tx_timer:
                    # data has been sent, waiting for reply
                    telapsed = time.time() - self.tx_timer
                    if telapsed > self.respond_timeout:
                        # no response to transmission self.respond_timeout seconds ago
                       writer.close()
                       await writer.wait_closed()
                       self._clear_connection()
                       if not self._stop:
                           await self.report("Error: Connection timed out")
            if self.connected and self._stop:
                writer.close()
                await writer.wait_closed()
                self._clear_connection()
        except Exception:
            logger.exception("Error in IPyClient._check_alive method")
            raise
        finally:
            self.connected = False

    def _logtx(self, txdata):
        "log tx data with level debug, and detail depends on self._verbose"
        if not self._verbose:
            return
        startlog = "TX:: "
        if self._verbose == 3:
            binarydata = ET.tostring(txdata)
            logger.debug(startlog + binarydata.decode())
        elif self._verbose == 2:
            if txdata.tag == "newBLOBVector" or txdata.tag == "setBLOBVector":
                data = copy.deepcopy(txdata)
                for element in data:
                    element.text = "NOT LOGGED"
                binarydata = ET.tostring(data)
            else:
                binarydata = ET.tostring(txdata)
            logger.debug(startlog + binarydata.decode())
        elif self._verbose == 1:
            data = copy.deepcopy(txdata)
            for element in data:
                data.remove(element)
            data.text = ""
            binarydata = ET.tostring(data, short_empty_elements=False).split(b">")
            logger.debug(startlog + binarydata[0].decode()+">")


    async def _run_tx(self, writer):
        "Monitors self._writerque and if it has data, uses writer to send it"
        try:
            while self.connected and (not self._stop):
                try:
                    txdata = await asyncio.wait_for(self._writerque.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                self._writerque.task_done()
                if not self.connected:
                    break
                if self._stop:
                    break
                # send it out on the port
                binarydata = ET.tostring(txdata)
                # Send to the port
                writer.write(binarydata)
                await writer.drain()
                if self.timeout_enable:
                    # data has been transmitted set timers going, do not set timer
                    # for enableBLOB as no answer is expected for that
                    if (self.tx_timer is None) and (txdata.tag != "enableBLOB"):
                        self.tx_timer = time.time()
                self.idle_timer = time.time()
                if logger.isEnabledFor(logging.DEBUG):
                    self._logtx(txdata)
        except Exception:
            logger.exception("Exception report from IPyClient._run_tx method")
            raise

    def _logrx(self, rxdata):
        "log rx data to file"
        if not self._verbose:
            return
        startlog = "RX:: "
        if self._verbose == 3:
            binarydata = ET.tostring(rxdata)
            logger.debug(startlog + binarydata.decode())
        elif self._verbose == 2:
            data = copy.deepcopy(rxdata)
            tag = data.tag
            for element in data:
                if tag  == "newBLOBVector":
                    element.text = "NOT LOGGED"
            binarydata = ET.tostring(data)
            logger.debug(startlog + binarydata.decode())
        elif self._verbose == 1:
            data = copy.deepcopy(rxdata)
            for element in data:
                data.remove(element)
            data.text = ""
            binarydata = ET.tostring(data, short_empty_elements=False).split(b">")
            logger.debug(startlog + binarydata[0].decode() + ">")

    async def _run_rx(self, reader):
        "pass xml.etree.ElementTree data to readerque"
        try:
            # get block of xml.etree.ElementTree data
            # from self._xmlinput and append it to  readerque
            while self.connected and (not self._stop):
                rxdata = await self._xmlinput(reader)
                if rxdata is None:
                    return
                # and place rxdata into readerque
                result = await self.queueput(self._readerque, rxdata, 0.2)
                if not result:
                    # self._stop must be set
                    return
                # rxdata in readerque, log it, then continue with next block
                if logger.isEnabledFor(logging.DEBUG):
                    self._logrx(rxdata)
        except Exception:
            logger.exception("Exception report from IPyClient._run_rx")
            raise


    async def _xmlinput(self, reader):
        """get received data, parse it, and return it as xml.etree.ElementTree object
           Returns None if notconnected/stop flags arises"""
        message = b''
        messagetagnumber = None
        while self.connected and (not self._stop):
            await asyncio.sleep(0)
            data = await self._datainput(reader)
            # data is either None, or binary data ending in b">"
            if data is None:
                return
            if not self.connected:
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
                    except ET.ParseError as e:
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
                except ET.ParseError as e:
                    # failed to parse the message, continue at beginning
                    message = b''
                    messagetagnumber = None
                    continue
                # xml datablock done, return it
                return root
            # so message is in progress, with a messagetagnumber set
            # but no valid endtag received yet, so continue the loop


    async def _datainput(self, reader):
        """Waits for binary string of data ending in > from the port
           Returns None if notconnected/stop flags arises"""
        binarydata = b""
        while self.connected and (not self._stop):
            await asyncio.sleep(0)
            try:
                data = await reader.readuntil(separator=b'>')
            except asyncio.LimitOverrunError:
                data = await reader.read(n=32000)
            except asyncio.IncompleteReadError:
                binarydata = b""
                continue
            if not data:
                await asyncio.sleep(0.01)
                continue
            # data received
            self.tx_timer = None
            self.idle_timer = time.time()
            if b">" in data:
                binarydata = binarydata + data
                return binarydata
            # data has content but no > found
            binarydata += data
            # could put a max value here to stop this increasing indefinetly


    async def _rxhandler(self):
        """Populates the events using data from self._readerque"""
        try:
            while not self._stop:
                # get block of data from the self._readerque
                try:
                    root = await asyncio.wait_for(self._readerque.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # nothing to read, continue while loop which re-checks the _stop flag
                    continue
                devicename = root.get("device")
                try:
                    if devicename is None:
                        if root.tag == "message":
                            # create event
                            event = events.Message(root, None, self)
                        elif root.tag == "getProperties":
                            # create event
                            event = events.getProperties(root, None, self)
                        else:
                            # if no devicename and not message or getProperties, do nothing
                            continue
                    elif devicename in self:
                        # device is known about
                        device = self[devicename]
                        event = device.rxvector(root)
                    elif root.tag == "getProperties":
                        # device is not known about, but this is a getProperties, so raise an event
                        event = events.getProperties(root, None, self)
                    elif root.tag in DEFTAGS:
                        # device not known, but a def is received
                        newdevice = Device(devicename, self)
                        event = newdevice.rxvector(root)
                        # no error has occurred, so add this device to self.data
                        self.data[devicename] = newdevice
                    else:
                        # device not known, not a def or getProperties, so ignore it
                        continue
                except ParseException as pe:
                    # if a ParseException is raised, it is because received data is malformed
                    await self.report(str(pe))
                    continue
                finally:
                    self._readerque.task_done()
                # and to get here, continue has not been called
                # and an event has been created, call the user event handling function
                await self.rxevent(event)

        except Exception:
            logger.exception("Exception report from IPyClient._rxhandler method")
            raise
        finally:
            self.shutdown()


    def snapshot(self):
        """Take a snapshot of the client and returns an object which is a restricted copy
           of the current state of devices and vectors.
           Vector methods for sending data will not be available.
           These copies will not be updated by events. This is provided so that you can
           handle the client data, without fear of their values changing."""

        snap = Snap(self.indihost, self.indiport, self.connected, self.messages)
        if self.data:
            for devicename, device in self.data.items():
                snap[devicename] = device.snapshot()
        # return the snapshot
        return snap


    async def send_newVector(self, devicename, vectorname, timestamp=None, members={}):
        """Send a Vector with updated member values, members is a membername
           to value dictionary. Note, if this vector is a BLOB Vector, the members
           dictionary should be {membername:(value, blobsize, blobformat)}"""
        device = self.data.get(devicename)
        if device is None:
            return
        propertyvector = device.get(vectorname)
        if propertyvector is None:
            return
        try:
            if propertyvector.vectortype == "SwitchVector":
                await propertyvector.send_newSwitchVector(timestamp, members)
            elif propertyvector.vectortype == "TextVector":
                await propertyvector.send_newTextVector(timestamp, members)
            elif propertyvector.vectortype == "NumberVector":
                await propertyvector.send_newNumberVector(timestamp, members)
            elif propertyvector.vectortype == "BLOBVector":
                await propertyvector.send_newBLOBVector(timestamp, members)
        except Exception:
            logger.exception("Exception report from IPyClient.send_newVector method")
            raise


    def set_vector_timeouts(self, timeout_enable=None, timeout_min=None, timeout_max=None):
        """The INDI protocol allows the server to suggest a timeout for each vector. This
           method allows you to set minimum and maximum timeouts which restricts the
           suggested values.

           These should be given as integer seconds. If any parameter
           is not provided (left at None) then that value will not be changed.

           If timeout_enable is set to False, no VectorTimeOut events will occur.

           As default, timeouts are enabled, minimum is set to 2 seconds, maximum 10 seconds.
           """
        if not timeout_enable is None:
            self.timeout_enable = timeout_enable
        if not timeout_min is None:
            self.vector_timeout_min = timeout_min
        if not timeout_max is None:
            self.vector_timeout_max = timeout_max
            self.idle_timeout = 2 * timeout_max
            self.respond_timeout = 4 * timeout_max


    async def _timeout_monitor(self):
        """Sends a getProperties every five seconds if no devices have been learnt
           or every self.idle_timeout seconds if nothing has been transmitted or received"""
        try:
            count = 0
            while (not self._stop):
                await asyncio.sleep(0.5)
                # This loop tests timeout values every half second
                if not self.connected:
                    count = 0
                else:
                    # so the connection is up, check enabled devices exist
                    if self.enabledlen():
                        # connection is up and devices exist
                        if self.timeout_enable:
                            # If nothing has been sent or received
                            # for self.idle_timeout seconds, send a getProperties
                            nowtime = time.time()
                            telapsed = nowtime - self.idle_timer
                            if telapsed > self.idle_timeout:
                                await self.send_getProperties()
                            # check if any vectors have timed out
                            for device in self.data.values():
                                for vector in device.values():
                                    if not vector.enable:
                                        continue
                                    if vector.checktimedout(nowtime):
                                        # Creat a VectorTimeOut event
                                        event = events.VectorTimeOut(device, vector)
                                        await self.rxevent(event)
                    else:
                        # no devices
                        # then send a getProperties, every five seconds, when count is zero
                        if not count:
                            await self.send_getProperties()
                            await self.report("getProperties sent")
                        count += 1
                        if count >= 10:
                            count = 0
        except Exception:
            logger.exception("Exception report from IPyClient._timeout_monitor method")
            raise
        finally:
            self.shutdown()


    async def send_getProperties(self, devicename=None, vectorname=None):
        """Sends a getProperties request. On startup the IPyClient object
           will automatically send getProperties, so typically you will
           not have to use this method."""
        if self.connected:
            xmldata = ET.Element('getProperties')
            xmldata.set("version", "1.7")
            if not devicename:
                await self.send(xmldata)
                return
            xmldata.set("device", devicename)
            if vectorname:
                xmldata.set("name", vectorname)
            await self.send(xmldata)

    async def send_enableBLOB(self, value, devicename, vectorname=None):
        """Sends an enableBLOB instruction. The value should be one of "Never", "Also", "Only"."""
        if self.connected:
            if value not in ("Never", "Also", "Only"):
                return
            xmldata = ET.Element('enableBLOB')
            if not devicename:
                # a devicename is required
                return
            xmldata.set("device", devicename)
            if vectorname:
                xmldata.set("name", vectorname)
            xmldata.text = value
            await self.send(xmldata)

    def get_vector_state(self, devicename, vectorname):
        """Gets the state string of the given vectorname, if this vector does not exist
           returns None - this could be because the vector is not yet learnt.
           The vector state attribute will still be returned, even if vector.enable is False"""
        device = self.data.get(devicename)
        if device is None:
            return
        propertyvector = device.get(vectorname)
        if propertyvector is None:
            return
        return propertyvector.state


    async def rxevent(self, event):
        """Override this.
           On receiving data, this is called, and should handle any necessary actions.
           event is an object with attributes according to the data received."""
        pass


    async def asyncrun(self):
        "Await this method to run the client."
        self._stop = False
        try:
            await asyncio.gather(self._comms(), self._rxhandler(), self._timeout_monitor(), self.hardware())
        finally:
            self.stopped.set()
            self._stop = True



class Snap(collections.UserDict):

    """An instance of this object is returned when a snapshot is
       taken of the client.
       It is a mapping of device name to device snapshots, which
       are in turn mappings of vectorname to vector snapshots.
       These snapshots record values and attributes, at the
       moment of the snapshot.
       Unlike IPyClient this has no send_newVector method, and the
       snap vectors do not have the send methods."""

    def __init__(self, indihost, indiport, connected, messages):
        super().__init__()
        self.indihost = indihost
        self.indiport = indiport
        self.connected = connected
        self.messages = list(messages)


    def enabledlen(self):
        "Returns the number of enabled devices"
        return sum(map(lambda x:1 if x.enable else 0, self.data.values()))


    def get_vector_state(self, devicename, vectorname):
        """Gets the state string of the given vectorname, if this vector does not exist
           returns None"""
        device = self.data.get(devicename)
        if device is None:
            return
        propertyvector = device.get(vectorname)
        if propertyvector is None:
            return
        return propertyvector.state


    def dictdump(self):
        """Returns a dictionary of this client information
           and is used to generate the JSON output"""
        messlist = []
        for message in self.messages:
            messlist.append([message[0].isoformat(sep='T'), message[1]])
        devdict = {}
        for devicename, device in self.items():
            devdict[devicename] = device.dictdump()
        return {"indihost":self.indihost,
                "indiport":self.indiport,
                "connected":self.connected,
                "messages":messlist,
                "enable":self.enable,
                "devices":devdict}

    def dumps(self, indent=None, separators=None):
        "Returns a JSON string of the snapshot."
        return json.dumps(self.dictdump(), indent=indent, separators=separators)


    def dump(self, fp, indent=None, separators=None):
        """Serialize the snapshot as a JSON formatted stream to fp, a file-like object.
           This uses the Python json module which always produces str objects, not bytes
           objects. Therefore, fp.write() must support str input."""
        return json.dump(self.dictdump(), fp, indent=indent, separators=separators)



class _ParentDevice(collections.UserDict):
    "Each device is a mapping of vector name to vector object."

    def __init__(self, devicename):
        super().__init__()
        # self.data is created by UserDict and will become a
        # dictionary of vector name to vector this device owns

        # This device name
        self.devicename = devicename


    @property
    def enable(self):
        "Returns True if any vector of this device has enable True, otherwise False"
        for vector in self.data.values():
            if vector.enable:
                return True
        return False

    def disable(self):
        "If called, disables the device"
        for vector in self.data.values():
            vector.enable = False


class SnapDevice(_ParentDevice):
    """This object is used as a snapshot of this device
       It is a mapping of vector name to vector snapshots"""

    def __init__(self, devicename, messages):
        super().__init__(devicename)
        self.messages = list(messages)

    def dictdump(self):
        """Returns a dictionary of this device information
           and is used to generate the JSON output"""
        messlist = []
        for message in self.messages:
            messlist.append([message[0].isoformat(sep='T'), message[1]])
        vecdict = {}
        for vectorname, vector in self.items():
            vecdict[vectorname] = vector.dictdump()
        return {"devicename":self.devicename, "messages":messlist, "enable":self.enable, "vectors":vecdict}

    def dumps(self, indent=None, separators=None):
        "Returns a JSON string of the snapshot."
        return json.dumps(self.dictdump(), indent=indent, separators=separators)


    def dump(self, fp, indent=None, separators=None):
        """Serialize the snapshot as a JSON formatted stream to fp, a file-like object.
           This uses the Python json module which always produces str objects, not bytes
           objects. Therefore, fp.write() must support str input."""
        return json.dump(self.dictdump(), fp, indent=indent, separators=separators)



class Device(_ParentDevice):

    """An instance of this is created for each device
       as data is received.
    """

    def __init__(self, devicename, client):
        super().__init__(devicename)

        # and the device has a reference to its client
        self._client = client

        # self.messages is a deque of tuples (timestamp, message)
        self.messages = collections.deque(maxlen=8)


    def __setitem__(self, propertyname, propertyvector):
        "Properties are added by being learnt from the driver, they cannot be manually added"
        raise KeyError


    def rxvector(self, root):
        """Handle received data, sets new propertyvector into self.data,
           or updates existing property vector and returns an event"""
        try:
            if root.tag == "delProperty":
                return events.delProperty(root, self, self._client)
            elif root.tag == "message":
                return events.Message(root, self, self._client)
            elif root.tag == "defSwitchVector":
                return events.defSwitchVector(root, self, self._client)
            elif root.tag == "setSwitchVector":
                return events.setSwitchVector(root, self, self._client)
            elif root.tag == "defLightVector":
                return events.defLightVector(root, self, self._client)
            elif root.tag == "setLightVector":
                return events.setLightVector(root, self, self._client)
            elif root.tag == "defTextVector":
                return events.defTextVector(root, self, self._client)
            elif root.tag == "setTextVector":
                return events.setTextVector(root, self, self._client)
            elif root.tag == "defNumberVector":
                return events.defNumberVector(root, self, self._client)
            elif root.tag == "setNumberVector":
                return events.setNumberVector(root, self, self._client)
            elif root.tag == "defBLOBVector":
                return events.defBLOBVector(root, self, self._client)
            elif root.tag == "setBLOBVector":
                return events.setBLOBVector(root, self, self._client)
            elif root.tag == "getProperties":
                return events.getProperties(root, self, self._client)
            else:
                raise ParseException("Unrecognised tag received")
        except ParseException:
            raise
        except Exception:
            logger.exception("Exception report from IPyClient.rxvector method")
            raise ParseException("Error while attempting to parse received data")


    def snapshot(self):
        """Take a snapshot of the device and returns an object which is a restricted copy
           of the current state of the device and its vectors.
           Vector methods for sending data will not be available.
           This copy will not be updated by events. This is provided so that you can
           handle the device data, without fear of the value changing."""
        snapdevice = SnapDevice(self.devicename, self.messages)
        for vectorname, vector in self.data.items():
            snapdevice[vectorname] = vector.snapshot()
        return snapdevice
