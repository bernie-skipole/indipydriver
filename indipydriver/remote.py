
import asyncio

import xml.etree.ElementTree as ET

from datetime import datetime, timezone

import logging
logger = logging.getLogger(__name__)

# All xml data received from the remote connection should be contained in one of the following tags
TAGS = (b'message',
        b'newTextVector',
        b'newNumberVector',
        b'newSwitchVector',
        b'newBLOBVector',
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


# Note these are strings, as they are used for checking xmldata.tag values

DEFTAGS = ( 'defSwitchVector',
            'defLightVector',
            'defTextVector',
            'defNumberVector',
            'defBLOBVector'
          )

NEWTAGS = ('newTextVector',
           'newNumberVector',
           'newSwitchVector',
           'newBLOBVector'
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

        #  These can be True or False.
        self.blob_enable = blob_enable
        self.debug_enable = debug_enable

        # This is a set of devicenames learnt on this remote connection
        # populated as devices are learnt, and used to check for duplicate names
        self.devicenames = set()

        self.alldrivers = alldrivers
        self.remotes= remotes
        self.serverwriterque = serverwriterque
        self.connectionpool = connectionpool

        # create queue where client will put xml data to be transmitted
        self._writerque = asyncio.Queue(4)

        # and create readerque where received xmldata will be put
        self._readerque = asyncio.Queue(4)

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
                    self.devicenames.clear()
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
                try:
                    # start by openning a connection
                    await self.warning(f"Attempting to connect to {self.indihost}:{self.indiport}")
                    reader, writer = await asyncio.open_connection(self.indihost, self.indiport)
                    self.connected = True
                    await self.warning(f"Connected to {self.indihost}:{self.indiport}")
                    t1 = asyncio.create_task(self._run_tx(writer))
                    t2 = asyncio.create_task(self._run_rx(reader))
                    await asyncio.gather(t1, t2)
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
                if self._stop:
                    break
                else:
                    await self.warning("Connection failed, re-trying...")
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


    def _logtx(self, txdata):
        "log tx data with level debug"
        if not self.debug_enable:
            return
        binarydata = ET.tostring(txdata)
        logger.debug("TX:: " + binarydata.decode())


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
                if not self.blob_enable:
                    if (txdata.tag == "setBLOBVector") or  (txdata.tag == "newBLOBVector"):
                        # blobs not enabled
                        continue
                # send it out on the port
                binarydata = ET.tostring(txdata)
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
        finally:
            writer.close()
            await writer.wait_closed()
            self.connected = False

    def _logrx(self, rxdata):
        "log rx data"
        if not self.debug_enable:
            return
        binarydata = ET.tostring(rxdata)
        logger.debug("RX:: " + binarydata.decode())


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
                    except ET.ParseError:
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
                except ET.ParseError:
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
        """Handles received data from self._readerque"""
        try:
            while not self._stop:
                # get block of data from the self._readerque
                try:
                    rxdata = await asyncio.wait_for(self._readerque.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    # nothing to read, continue while loop which re-checks the _stop flag
                    continue
                self._readerque.task_done()

                devicename = rxdata.get("device")
                vectorname = rxdata.get("name")

                if not self.blob_enable:
                    if rxdata.tag in ("setBLOBVector", "newBLOBVector"):
                        # blobs not enabled
                        continue

                if devicename:
                    if rxdata.tag in DEFTAGS:
                        # check for duplicate devicename
                        for driver in self.alldrivers:
                            if devicename in driver:
                                logger.error(f"A duplicate devicename {devicename} has been detected")
                                await self.queueput(self.serverwriterque, None)
                                return
                        for remote in self.remotes:
                            if remote is self:
                                continue
                            if devicename in remote.devicenames:
                                logger.error(f"A duplicate devicename {devicename} has been detected")
                                await self.queueput(self.serverwriterque, None)
                                return
                        if devicename not in self.devicenames:
                            self.devicenames.add(devicename)
                        if rxdata.tag == "defBLOBVector":
                            # every time a defBLOBVector is received, send an enable BLOB instruction
                            xmldata = ET.Element('enableBLOB')
                            xmldata.set("device", devicename)
                            xmldata.set("name", vectorname)
                            if self.blob_enable:
                                xmldata.text = "Also"
                            else:
                                xmldata.text = "Never"
                            await self.send(xmldata)

                    # if a new vector or a getProperties has been received, and is targetted at a
                    # driver, send it to the driver and nowhere else
                    if (rxdata.tag in NEWTAGS) or (rxdata.tag == "getProperties"):
                        dfound = False
                        for driver in self.alldrivers:
                            if devicename in driver:
                                await self.queueput(driver.readerque, rxdata)
                                # no need to transmit this anywhere else
                                dfound = True
                                break
                        if dfound:
                            continue

                # so not targetted at a local known devicename
                # transmit to drivers if rxdata is either a getProperties or because the driver is snooping on it

                if rxdata.tag == "getProperties":
                    for driver in self.alldrivers:
                        # either no devicename, or an unknown device, so send to all drivers
                        await self.queueput(driver.readerque, rxdata)
                elif rxdata.tag not in NEWTAGS:
                    for driver in self.alldrivers:
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

                # transmit rxdata out to other remote connections
                for remcon in self.remotes:
                    if remcon is self:
                        continue
                    await remcon.send(rxdata)

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
