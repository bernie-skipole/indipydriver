
import asyncio

import xml.etree.ElementTree as ET

from datetime import datetime, timezone

import logging
logger = logging.getLogger(__name__)

#from indipyclient import IPyClient

#from indipyclient.events import getProperties


# All xml data received from the remote connection should be contained in one of the following tags
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
        b'getProperties'
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


class ParseException(Exception):
    "Raised if an error occurs when parsing received data"
    pass



class RemoteConnection:


    def __init__(self, host, port,
                       alldrivers,      # list of drivers connected to the server
                       remotes,         # list of RemoteConnection(s) connected to the server
                       serverwriterque, # queue of items for the server to transmit
                       connectionpool   # pool of connections calling this server
                 )


        self.indihost = host
        self.indiport = port
        self.alldrivers = alldrivers
        self.remotes= remotes
        self.serverwriterque = serverwriterque
        self.connectionpool = connectionpool

        self.snoopall = False           # gets set to True if it is snooping everything
        self.snoopdevices = set()       # gets set to a set of device names
        self.snoopvectors = set()       # gets set to a set of (devicename,vectorname) tuples


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

        # set and unset BLOBfolder
        self._BLOBfolder = None
        self._blobfolderchanged = False
        # This is the default enableBLOB value
        self._enableBLOBdefault = "Never"


    # The enableBLOBdefault default should typically be set before asyncrun is
    # called, so if set to Also, this will ensure all BLOBs will be received without
    # further action
    @property
    def enableBLOBdefault(self):
        return self._enableBLOBdefault

    @enableBLOBdefault.setter
    def enableBLOBdefault(self, value):
        if value in ("Never", "Also", "Only"):
            self._enableBLOBdefault = value

    # Setting a BLOBfolder forces all BLOBs will be received and saved as files to the given folder

    def _get_BLOBfolder(self):
        return self._BLOBfolder

    def _set_BLOBfolder(self, value):
        """Setting the BLOBfolder to a folder will automatically set all devices to Also
           Setting it to None, will set all devices to self._enableBLOBdefault"""
        if value:
            if isinstance(value, pathlib.Path):
                blobpath = value
            else:
                blobpath = pathlib.Path(value).expanduser().resolve()
            if not blobpath.is_dir():
                raise KeyError("If given, the BLOB's folder should be an existing directory")
            for device in self.values():
                device._enableBLOB = "Also"
                for vector in device.values():
                    if vector.vectortype == "BLOBVector":
                        vector._enableBLOB = "Also"
        else:
            blobpath = None
            if self._BLOBfolder is None:
                # no change
                return
            for device in self.values():
                device._enableBLOB = self._enableBLOBdefault
                for vector in device.values():
                    if vector.vectortype == "BLOBVector":
                        vector._enableBLOB = self._enableBLOBdefault
        self._BLOBfolder = blobpath
        self._blobfolderchanged = True


    BLOBfolder = property(
        fget=_get_BLOBfolder,
        fset=_set_BLOBfolder,
        doc= """Setting the BLOBfolder to a folder will automatically transmit an enableBLOB
for all devices set to Also, and will save incoming BLOBs to that folder.
Setting it to None will transmit an enableBLOB for all devices set to the enableBLOBdefault value"""
        )







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
        """If connection fails, for each device learnt, disable it"""
        isconnected = False
        while not self._stop:
            await asyncio.sleep(0.1)
            if self.connected:
                if isconnected:
                    continue
                isconnected = True
                # a new connection has been made
                await self.send_getProperties()
                for clientconnection in self.connectionpool:
                    if clientconnection.connected:
                        # a client is connected, send a message
                        timestamp = datetime.now(tz=timezone.utc)
                        timestamp = timestamp.replace(tzinfo = None)
                        tstring = timestamp.isoformat(sep='T')
                        messagedata = ET.Element('message')
                        messagedata.set("timestamp", tstring)
                        messagedata.set("message", f"Remote connection made to {self.indihost}:{self.indiport}")
                        await self.queueput(self.serverwriterque, messagedata)
                        break
                continue
            # The connection has failed
            isconnected = False
            if self.enabledlen():
                # some devices are enabled, disable them
                timestamp = datetime.now(tz=timezone.utc)
                timestamp = timestamp.replace(tzinfo = None)
                tstring = timestamp.isoformat(sep='T')
                # If no clients are connected, do not send data into
                # the serverwriterque
                clientconnected = False
                for clientconnection in self.connectionpool:
                    if clientconnection.connected:
                        clientconnected = True
                        break
                # send a message
                if clientconnected:
                    messagedata = ET.Element('message')
                    messagedata.set("timestamp", tstring)
                    messagedata.set("message", f"Remote connection to {self.indihost}:{self.indiport} lost")
                    await self.queueput(self.serverwriterque, messagedata)
                for devicename, device in self.items():
                    if device.enable:
                        device.disable()
                        if clientconnected:
                            xmldata = ET.Element('delProperty')
                            xmldata.set("device", devicename)
                            xmldata.set("timestamp", tstring)
                            xmldata.set("message", f"Remote Connection lost, {devicename} disabled")
                            await self.queueput(self.serverwriterque, xmldata)





    def shutdown(self):
        "Shuts down the client, sets the flag self._stop to True"
        self._stop = True

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the client"
        return self._stop


    async def queueput(self, queue, value, timeout=0.5):
        """Method used internally, but available if usefull.
           Given an asyncio.Queue object attempts to put value into the queue.
           If the queue is full, checks self._stop every timeout seconds.
           Returns True when the value is added to queue,
           or False if self._stop is True and the value not added."""
        while not self._stop:
            try:
                await asyncio.wait_for(queue.put(value), timeout)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            return True
        return False


    async def warning(self, message):
        """The given string message will be logged at level WARNING,
           and will be injected into the received data, which will be
           picked up by the rxevent method.
           It is a way to set a message on to your client display, in the
           same way messages come from the INDI service."""
        try:
            logger.warning(message)
            timestamp = datetime.now(tz=timezone.utc)
            timestamp = timestamp.replace(tzinfo=None)
            root = ET.fromstring(f"<message timestamp=\"{timestamp.isoformat(sep='T')}\" message=\"{message}\" />")
            # and place root into readerque
            await self.queueput(self._readerque, root)
        except Exception :
            logger.exception("Exception report from IPyClient.warning method")


    def enabledlen(self):
        "Returns the number of enabled devices"
        return sum(map(lambda x:1 if x.enable else 0, self.data.values()))


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
                    await self.warning(f"Attempting to connect to {self.indihost}:{self.indiport}")
                    reader, writer = await asyncio.open_connection(self.indihost, self.indiport)
                    self.connected = True
                    self.messages.clear()
                    # clear devices etc
                    self.clear()
                    await self.warning(f"Connected to {self.indihost}:{self.indiport}")
                    t1 = asyncio.create_task(self._run_tx(writer))
                    t2 = asyncio.create_task(self._run_rx(reader))
                    t3 = asyncio.create_task(self._check_alive(writer))
                    await asyncio.gather(t1, t2, t3)
                except ConnectionRefusedError:
                    await self.warning(f"Connection refused on {self.indihost}:{self.indiport}")
                except ConnectionError:
                    await self.warning(f"Connection Lost on {self.indihost}:{self.indiport}")
                except OSError:
                    await self.warning(f"Connection Error on {self.indihost}:{self.indiport}")
                except Exception:
                    logger.exception(f"Connection Error on {self.indihost}:{self.indiport}")
                    await self.warning("Connection failed")
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
                    await self.warning(f"Connection failed, re-trying...")
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
                           await self.warning("Error: Connection timed out")
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
        except ConnectionError:
            raise
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
        except ConnectionError:
            raise
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
                await asyncio.sleep(0.1)
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
                    await self.warning(str(pe))
                    continue
                finally:
                    self._readerque.task_done()
                # and to get here, continue has not been called
                # and an event has been created,

                if event.eventtype == "DefineBLOB":
                    # every time a defBLOBVector is received, send an enable BLOB instruction
                    await self.resend_enableBLOB(event.devicename, event.vectorname)
                elif self._BLOBfolder and (event.eventtype == "SetBLOB"):
                    # If this event is a setblob, and if blobfolder has been defined, then save the blob to
                    # a file in blobfolder, and set the member.filename to the filename saved
                    loop = asyncio.get_running_loop()
                    # save the BLOB to a file, make filename from timestamp
                    timestampstring = event.timestamp.strftime('%Y%m%d_%H_%M_%S')
                    for membername, membervalue in event.items():
                        if not membervalue:
                            continue
                        sizeformat = event.sizeformat[membername]
                        filename =  membername + "_" + timestampstring + sizeformat[1]
                        counter = 0
                        while True:
                            filepath = self._BLOBfolder / filename
                            if filepath.exists():
                                # append a digit to the filename
                                counter += 1
                                filename = membername + "_" + timestampstring + "_" + str(counter) + sizeformat[1]
                            else:
                                # filepath does not exist, so a new file with this filepath can be created
                                break
                        await loop.run_in_executor(None, filepath.write_bytes, membervalue)
                        # add filename to member
                        memberobj = event.vector.member(membername)
                        memberobj.filename = filename

                # call the user event handling function
                await self.rxevent(event)

        except Exception:
            logger.exception("Exception report from IPyClient._rxhandler method")
            raise
        finally:
            self.shutdown()



    async def send_newVector(self, devicename, vectorname, timestamp=None, members={}):
        """Send a Vector with updated member values, members is a membername
           to value dictionary.

           Note, if this vector is a BLOB Vector, the members dictionary should be
           {membername:(value, blobsize, blobformat)}
           where value could be a bytes object, a pathlib.Path, or a string filepath.
           If blobsize of zero is used, the size value sent will be set to the number of bytes
           in the BLOB. The INDI standard specifies the size should be that of the BLOB
           before any compression, therefore if you are sending a compressed file, you
           should set the blobsize prior to compression.
           blobformat should be a file extension, such as '.png'. If it is an empty string
           and value is a filename, the extension will be taken from the filename."""

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
                    devices = list(device for device in self.data.values() if device.enable)
                    if devices:
                        # connection is up and devices exist
                        if self._blobfolderchanged:
                            # devices all have an _enableBLOB attribute set
                            # when the BLOBfolder changed, this ensures an
                            # enableBLOB is sent with that value
                            self._blobfolderchanged = False
                            for device in devices:
                                if self._stop:
                                    break
                                await self.resend_enableBLOB(device.devicename)
                                if self._stop:
                                    break
                                for vector in device.values():
                                    if vector.enable and (vector.vectortype == "BLOBVector"):
                                        await self.resend_enableBLOB(device.devicename, vector.name)
                                        if self._stop:
                                            break
                            # as enableBLOBs have been sent, leave
                            # checking timeouts for the next .5 second
                            continue
                        if self.timeout_enable:
                            # If nothing has been sent or received
                            # for self.idle_timeout seconds, send a getProperties
                            nowtime = time.time()
                            telapsed = nowtime - self.idle_timer
                            if telapsed > self.idle_timeout:
                                await self.send_getProperties()
                            # check if any vectors have timed out
                            for device in devices:
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
                            logger.info("getProperties sent")
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
            if devicename not in self:
                return
            device = self[devicename]
            if not device.enable:
                return
            xmldata.set("device", devicename)
            if vectorname:
                if vectorname not in device:
                    return
                vector = device[vectorname]
                if not vector.enable:
                    return
                if vector.vectortype != "BLOBVector":
                    return
                xmldata.set("name", vectorname)
                vector._enableBLOB = value
            else:
                # no vectorname, so this applies to all BLOB vectors of this device
                device._enableBLOB = value
                for vector in device.values():
                    if vector.vectortype == "BLOBVector":
                        vector._enableBLOB = value
            xmldata.text = value
            await self.send(xmldata)


    async def resend_enableBLOB(self, devicename, vectorname=None):
        """Internal method used by the framework, which sends an enableBLOB instruction,
           repeating the last value sent.
           Used as an automatic reply to a def packet received, if no last value sent
           the default is the enableBLOBdefault value."""
        if self.connected:
            xmldata = ET.Element('enableBLOB')
            if not devicename:
                # a devicename is required
                return
            if devicename not in self:
                return
            device = self[devicename]
            if not device.enable:
                return
            xmldata.set("device", devicename)
            if vectorname:
                if vectorname not in device:
                    return
                vector = device[vectorname]
                if not vector.enable:
                    return
                if vector.vectortype != "BLOBVector":
                    return
                xmldata.set("name", vectorname)
                value = vector._enableBLOB
            else:
                # no vectorname, so this applies to the device
                value = device._enableBLOB
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
        "Handle events as they are received on this connection"
        rxdata = event.root
        if rxdata is None:
            return

        devicename = event.devicename
        vectorname = event.vectorname

        # rxdata is the xml data received

        if event.eventtype == "Define" or event.eventtype == "DefineBLOB":
            # check for duplicate devicename
            for driver in self.alldrivers:
                if devicename in driver:
                    logger.error(f"A duplicate devicename {devicename} has been detected")
                    await self.queueput(self.serverwriterque, None)
                    return
            for remcon in self.remotes:
                if remcon is self:
                    continue
                if devicename in remcon:
                    logger.error(f"A duplicate devicename {devicename} has been detected")
                    await self.queueput(self.serverwriterque, None)
                    return


        # check for a getProperties event, record what is being snooped
        if isinstance(event, getProperties):
            if devicename is None:
                self.snoopall = True
            elif vectorname is None:
                self.snoopdevices.add(devicename)
            else:
                self.snoopvectors.add((devicename,vectorname))

            # if getproperties is targetted at a known device, send it to that device
            if devicename:
                for driver in self.alldrivers:
                    if devicename in driver:
                        # this getProperties request is meant for an attached device
                        await self.queueput(driver.readerque, rxdata)
                        # no need to transmit this anywhere else
                        return
                for remcon in self.remotes:
                    if remcon is self:
                        continue
                    if devicename in remcon:
                        # this getProperties request is meant for a remote connection
                        await remcon.send(rxdata)
                        # no need to transmit this anywhere else
                        return

        # transmit rxdata out to other remote connections
        # which occurs if they are snooping on devices on this link.
        for remcon in self.remotes:
            if remcon is self:
                continue
            if isinstance(event, getProperties):
                # either no devicename, or an unknown device
                # if it were a known devicename the previous block would have handled it.
                # so send it on all connections
                await remcon.send(rxdata)
            else:
                # Check if this remcon is snooping on this device/vector
                if remcon.snoopall:
                    await remcon.send(rxdata)
                elif devicename and (devicename in remcon.snoopdevices):
                    await remcon.send(rxdata)
                elif devicename and vectorname and ((devicename, vectorname) in remcon.snoopvectors):
                    await remcon.send(rxdata)

        # transmit rxdata out to drivers
        for driver in self.alldrivers:
            if isinstance(event, getProperties):
                # either no devicename, or an unknown device
                await self.queueput(driver.readerque, rxdata)
            else:
                # Check if this driver is snooping on this device/vector
                if driver.snoopall:
                    await self.queueput(driver.readerque, rxdata)
                elif devicename and (devicename in driver.snoopdevices):
                    await self.queueput(driver.readerque, rxdata)
                elif devicename and vectorname and ((devicename, vectorname) in driver.snoopvectors):
                    await self.queueput(driver.readerque, rxdata)

        # transmit rxdata out to clients

        # If no clients are connected, do not put this data into
        # the serverwriterque
        for clientconnection in self.connectionpool:
            if clientconnection.connected:
                # at least one is connected, so this data is put into
                # serverwriterque
                await self.queueput(self.serverwriterque, rxdata)
                break


    async def asyncrun(self):
        "Await this method to run the connectiont."
        self._stop = False
        try:
            await asyncio.gather(self._comms(), self._rxhandler(), self._timeout_monitor(), self.hardware())
        except asyncio.CancelledError:
            self._stop = True
            raise
        finally:
            self.stopped.set()
            self._stop = True
