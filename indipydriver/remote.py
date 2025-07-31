
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
                       debug_enable ):

        self.indihost = host
        self.indiport = port

        # These will be created when a connection is made using
        # await asyncio.open_connection(self.indihost, self.indiport)
        self._writer = None
        self._reader = None

        #  These can be True or False.
        self.blob_enable = blob_enable
        self.debug_enable = debug_enable

        # This is a set of devicenames learnt on this remote connection
        # populated as devices are learnt, and used to check for duplicate names
        self.devicenames = set()

        # An object for communicating is set when this remote is added to the server
        self._commsobj = None

        # and shutdown routine sets this to True to stop coroutines
        self._stop = False


    @property
    def connected(self):
        "property showing connected status, True or False"
        if self._writer is None:
            return False
        else:
            return True

    async def _clear_connection(self):
        "Clears a connection"
        try:
            if self._writer is not None:
                self._writer.close()
                await self._writer.wait_closed()
        except Exception:
            logger.exception("Exception report from RemoteConnection._clear_connection method")
        await self.warning(f"Connection closed on {self.indihost}:{self.indiport}")
        self._writer = None
        self._reader = None

    def __contains__(self, item):
        "So a devicename can easily be checked if it is in this driver"
        return item in self.devicenames


    async def _monitor_connection(self):
        """Flag connection made or failed messages into the server"""
        # create a flag so 'remote connection made' message is only set once
        isconnected = False
        while not self._stop:
            await asyncio.sleep(0.1)
            if self.connected:
                if isconnected:
                    continue
                isconnected = True
                # a new connection has been made, send a getProperties down the link
                await self.send_getProperties()
                # broadcast a message to everyone else connected to the server
                if self._commsobj is not None:
                    timestamp = datetime.now(tz=timezone.utc)
                    timestamp = timestamp.replace(tzinfo = None)
                    tstring = timestamp.isoformat(sep='T')
                    messagedata = ET.Element('message')
                    messagedata.set("timestamp", tstring)
                    messagedata.set("message", f"Remote connection made to {self.indihost}:{self.indiport}")
                    await self._commsobj.run_tx(messagedata)
            else:
                # The connection has failed
                if isconnected:
                    isconnected = False
                    self.devicenames.clear()
                    # broadcast a message to everyone else connected to the server
                    if self._commsobj is not None:
                        # send a message to everyone else connected to the server
                        timestamp = datetime.now(tz=timezone.utc)
                        timestamp = timestamp.replace(tzinfo = None)
                        tstring = timestamp.isoformat(sep='T')
                        messagedata = ET.Element('message')
                        messagedata.set("timestamp", tstring)
                        messagedata.set("message", f"Remote connection to {self.indihost}:{self.indiport} lost")
                        await self._commsobj.run_tx(messagedata)


    def shutdown(self):
        "Shuts down the client, sets the flag self._stop to True"
        self._stop = True
        if self._commsobj is not None:
            self._commsobj.shutdown()

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the client"
        return self._stop


    async def warning(self, message):
        """The given string message will be logged at level WARNING,
           and will be sent to all drivers and connections."""
        try:
            logger.warning(message)
            timestamp = datetime.now(tz=timezone.utc)
            timestamp = timestamp.replace(tzinfo=None)
            xmldata = ET.fromstring(f"<message timestamp=\"{timestamp.isoformat(sep='T')}\" message=\"{message}\" />")
            self._commsobj.run_tx_everywhere(xmldata)
        except Exception :
            logger.exception("Exception report from RemoteConnection.warning method")


    async def _create_connection(self):
        "Create a connection to an INDI port"
        try:
            while not self._stop:
                t1 = None
                t2 = None
                try:
                    # start by openning a connection
                    await self.warning(f"Attempting to connect to {self.indihost}:{self.indiport}")
                    self._reader, self._writer = await asyncio.open_connection(self.indihost, self.indiport)
                    await self.warning(f"Connected to {self.indihost}:{self.indiport}")
                    await self._run_rx()
                except ConnectionRefusedError:
                    await self.warning(f"Connection refused on {self.indihost}:{self.indiport}")
                except ConnectionError:
                    await self.warning(f"Connection Lost on {self.indihost}:{self.indiport}")
                except OSError:
                    await self.warning(f"Connection Error on {self.indihost}:{self.indiport}")
                except Exception:
                    logger.exception(f"Connection Error on {self.indihost}:{self.indiport}")
                    await self.warning("Connection failed")
                await self._clear_connection()
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
            logger.exception("Exception report from RemoteConnection._create_connection method")
            raise
        finally:
            await self._clear_connection()
            self.shutdown()


    async def send(self, xmldata):
        """Transmits xmldata, which is an xml.etree.ElementTree object out on the remote connection"""
        if not self.connected:
            return
        if self._stop:
            return
        try:
            if not self.blob_enable:
                if (xmldata.tag == "setBLOBVector") or  (xmldata.tag == "newBLOBVector"):
                    # blobs not enabled
                    return
            # send it out on the port
            binarydata = ET.tostring(xmldata)
            self._writer.write(binarydata)
            await self._writer.drain()
            # data has been transmitted
            if logger.isEnabledFor(logging.DEBUG):
                self._logtx(xmldata)
        except Exception:
            logger.exception(f"Sending error from RemoteConnection.send method for {self.indihost}:{self.indiport}")
            await self._clear_connection()


    async def _readdata(self, xmldata):
        """Called from communications object with  xmldata from other drivers
           . clients and connections. Sends it towards the remote connection"""
        if xmldata.tag == "enableBLOB":
            return
        self.send(xmldata)


    def _logtx(self, xmldata):
        "log tx data with level debug"
        if not self.debug_enable:
            return
        binarydata = ET.tostring(xmldata)
        logger.debug("TX:: " + binarydata.decode())


    def _logrx(self, rxdata):
        "log rx data"
        if not self.debug_enable:
            return
        binarydata = ET.tostring(rxdata)
        logger.debug("RX:: " + binarydata.decode())


    async def _run_rx(self):
        "accept xml.etree.ElementTree data from the connection"
        try:
            # get block of xml.etree.ElementTree data
            # from self._xmlinput
            while self.connected and (not self._stop):
                xmldata = await self._xmlinput()
                if xmldata is None:
                    return
                if (not self.blob_enable) and (xmldata.tag in ("setBLOBVector", "newBLOBVector") ):
                    # blobs not enabled
                    continue


                devicename = xmldata.get("device")
                vectorname = xmldata.get("name")

                if xmldata.tag in DEFTAGS:
                    if (devicename is None) or (vectorname is None):
                        continue
                    if devicename not in self.devicenames:
                        self.devicenames.add(devicename)
                    if xmldata.tag == "defBLOBVector":
                        # every time a defBLOBVector is received, send an enable BLOB instruction
                        senddata = ET.Element('enableBLOB')
                        senddata.set("device", devicename)
                        senddata.set("name", vectorname)
                        if self.blob_enable:
                            senddata.text = "Also"
                        else:
                            senddata.text = "Never"
                        await self.send(senddata)

                # and pass data to other drivers and connections
                await self._commsobj._run_tx(xmldata)
                # log it, then continue with next block
                if logger.isEnabledFor(logging.DEBUG):
                    self._logrx(rxdata)
        except ConnectionError:
            raise
        except Exception:
            logger.exception("Exception report from RemoteConnection._run_rx")
            raise




    async def _xmlinput(self):
        """get received data, parse it, and return it as xml.etree.ElementTree object
           Returns None if notconnected/stop flags arises"""
        message = b''
        messagetagnumber = None
        while self.connected and (not self._stop):
            await asyncio.sleep(0)
            data = await self._datainput()
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


    async def _datainput(self):
        """Waits for binary string of data ending in > from the port
           Returns None if notconnected/stop flags arises"""
        binarydata = b""
        while self.connected and (not self._stop):
            await asyncio.sleep(0)
            try:
                data = await self._reader.readuntil(separator=b'>')
            except asyncio.LimitOverrunError:
                data = await self._reader.read(n=32000)
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

            async with asyncio.TaskGroup() as tg:
                tg.create_task( self._create_connection() )
                tg.create_task( self._monitor_connection() )

        except Exception:
            logger.exception("Remote connection shutdown")
        finally:
            self._stop = True
