
import collections, asyncio, copy

import xml.etree.ElementTree as ET

from datetime import datetime, timezone

import logging
logger = logging.getLogger(__name__)

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


class RemoteConnection:

    def __init__(self, host, port,
                       blob_enable,
                       debug_enable,
                       alldrivers,      # list of drivers connected to the server
                       remotes,         # list of RemoteConnection(s) connected to the server
                       serverwriterque, # queue of items for the server to transmit
                       connectionpool   # pool of connections calling this server
                 ):

        self.indihost = host
        self.indiport = port

        #  blob_enable can be Never, Also or Only.
        #  If Never BLOBs will not be sent from the remote server to this one.
        #  If Also BLOBs and other vectors can all be sent.
        #  If Only, then only BLOB traffic will be sent.

        self.enableBLOBdefault = blob_enable

        if debug_enable:
            self._verbose = 2 # turn on xml logs
        else:
            self._verbose = 0 # turn off xml logs

        #  0 no xml logs will be generated
        #  1 for transmitted/received vector tags only,
        #  2 for transmitted/received vectors, members and contents (apart from BLOBs)
        #  3 for all transmitted/received data including BLOBs."""

        self.alldrivers = alldrivers
        self.remotes= remotes
        self.serverwriterque = serverwriterque
        self.connectionpool = connectionpool

        self.snoopall = False           # gets set to True if it is snooping everything
        self.snoopdevices = set()       # gets set to a set of device names
        self.snoopvectors = set()       # gets set to a set of (devicename,vectorname) tuples

        # self.devices is a set of devicenames, received by def packets
        self.devices = set()

        # self.blobvectors is a dictionary of devicename:set of blob vectornames received
        self.blobvectors = {}

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

        # and shutdown routine sets this to True to stop coroutines
        self._stop = False
        # this is set when asyncrun is finished
        self.stopped = asyncio.Event()



    async def _hardware(self):
        """Flag connection made or failed messages into serverwriterque"""
        # create a flag so 'remote connection made' message is only set once
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
            else:
                # The connection has failed
                if isconnected:
                    isconnected = False
                    for clientconnection in self.connectionpool:
                        if clientconnection.connected:
                            # a client is connected, send a message
                            timestamp = datetime.now(tz=timezone.utc)
                            timestamp = timestamp.replace(tzinfo = None)
                            tstring = timestamp.isoformat(sep='T')
                            messagedata = ET.Element('message')
                            messagedata.set("timestamp", tstring)
                            messagedata.set("message", f"Remote connection to {self.indihost}:{self.indiport} lost")
                            await self.queueput(self.serverwriterque, messagedata)
                            break


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
            logger.exception("Exception report from RemoteConnection.warning method")


    async def _comms(self):
        "Create a connection to an INDI port"
        try:
            while not self._stop:
                t1 = None
                t2 = None
                t3 = None
                try:
                    # start by openning a connection
                    await self.warning(f"Attempting to connect to {self.indihost}:{self.indiport}")
                    reader, writer = await asyncio.open_connection(self.indihost, self.indiport)
                    self.connected = True
                    self.messages.clear()
                    # clear devices
                    self.devices.clear()
                    self.blobvectors.clear()
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
                self.connected = False
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
                # clear devices
                self.devices.clear()
                self.blobvectors.clear()
                # wait five seconds before re-trying, but keep checking
                # that self._stop has not been set
                count = 0
                while not self._stop:
                    await asyncio.sleep(0.5)
                    count += 1
                    if count >= 10:
                        break
        except Exception:
            logger.exception("Exception report from RemoteConnection._comms method")
            raise
        finally:
            self.shutdown()


    async def send(self, xmldata):
        """Transmits xmldata, which is an xml.etree.ElementTree object"""
        if self.connected and (not self._stop):
            await self.queueput(self._writerque, xmldata)


    async def _check_alive(self, writer):
        try:
            while self.connected and (not self._stop):
                await asyncio.sleep(0.1)
            if self.connected and self._stop:
                writer.close()
                await writer.wait_closed()
        except Exception:
            logger.exception("Error in RemoteConnection._check_alive method")
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
                # data has been transmitted
                if logger.isEnabledFor(logging.DEBUG):
                    self._logtx(txdata)
        except ConnectionError:
            raise
        except Exception:
            logger.exception("Exception report from RemoteConnection._run_tx method")
            raise

    def _logrx(self, rxdata):
        "log rx data"
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
            logger.exception("Exception report from RemoteConnection._run_rx")
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
                        if root.tag != "message" and root.tag != "getProperties":
                            # if no devicename and not message or getProperties, do nothing
                            continue
                    elif devicename not in self.devices:
                        # device is not known about
                        if root.tag != "getProperties":
                            if root.tag in DEFTAGS:
                                # device not known, but a def is received
                                self.devices.add(devicename)
                            else:
                                # device not known, not a def or getProperties, so ignore it
                                continue
                except Exception:
                    # Received data is malformed
                    await self.warning("Received data malformed")
                    continue
                finally:
                    self._readerque.task_done()
                # and to get here, continue has not been called
                # and a root received xml packet has been created,

                if root.tag == "defBLOBVector":
                    # every time a defBLOBVector is received, send an enable BLOB instruction
                    # and record the vectorname
                    vectorname = root.get("name")
                    if devicename not in self.blobvectors:
                        self.blobvectors[devicename] = set()
                    if vectorname not in self.blobvectors[devicename]:
                        self.blobvectors[devicename].add(vectorname)
                    xmldata = ET.Element('enableBLOB')
                    xmldata.set("device", devicename)
                    xmldata.set("name", vectorname)
                    xmldata.text = self.enableBLOBdefault
                    await self.send(xmldata)

                # call the user event handling function
                await self.rxevent(root)

        except Exception:
            logger.exception("Exception report from RemoteConnection._rxhandler method")
            raise
        finally:
            self.shutdown()


    async def send_getProperties(self):
        """Sends a getProperties request"""
        if self.connected:
            xmldata = ET.Element('getProperties')
            xmldata.set("version", "1.7")
            await self.send(xmldata)


    async def rxevent(self, rxdata):
        "Handle events as they are received on this connection"
        if rxdata is None:
            return

        devicename = rxdata.get("device")
        vectorname = rxdata.get("name")

        # rxdata is the xml data received

        if devicename:
            if rxdata.tag in DEFTAGS:
                # check for duplicate devicename
                for driver in self.alldrivers:
                    if devicename in driver:
                        logger.error(f"A duplicate devicename {devicename} has been detected")
                        await self.queueput(self.serverwriterque, None)
                        return
                for remcon in self.remotes:
                    if remcon is self:
                        continue
                    if devicename in remcon.devices:
                        logger.error(f"A duplicate devicename {devicename} has been detected")
                        await self.queueput(self.serverwriterque, None)
                        return


        # check for a getProperties event, record what is being snooped
        if rxdata.tag == "getProperties":
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
                    if devicename in remcon.devices:
                        # this getProperties request is meant for a remote connection
                        await remcon.send(rxdata)
                        # no need to transmit this anywhere else
                        return

        # transmit rxdata out to other remote connections
        # which occurs if they are snooping on devices on this link.
        for remcon in self.remotes:
            if remcon is self:
                continue
            if rxdata.tag == "getProperties":
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
            if rxdata.tag == "getProperties":
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
            await asyncio.gather(self._comms(), self._rxhandler(), self._hardware())
        except asyncio.CancelledError:
            self._stop = True
            raise
        finally:
            self.stopped.set()
            self._stop = True
