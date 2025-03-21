
import asyncio, sys, os, time

import xml.etree.ElementTree as ET

import fcntl

import logging
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


async def queueget(queue, timeout=0.5):
    """"Returns True, True if timed out
                True, False is reserved for future
                False, Value if a value is taken from the queue"""
    try:
        value = await asyncio.wait_for(queue.get(), timeout)
    except asyncio.TimeoutError:
        return True, True
    return False, value


class STDOUT_TX:
    "An object that transmits data on stdout, used by STDINOUT as one half of the communications path"

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
            quexit, txdata = await queueget(writerque)
            if quexit:
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


class STDIN_RX:
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
            logger.exception("Exception report from STDIN_RX.run_rx")
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
                    except Exception as e:
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
                except Exception as e:
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



class STDINOUT():
    """If indipydriver.comms is set to an instance of this class it is
       used to implement communications via stdin and stdout"""

    def __init__(self):
        self.connected = True
        self.rx = STDIN_RX()
        self.tx = STDOUT_TX()
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

class Port_TX():
    "An object that transmits data on a port, used by Portcomms as one half of the communications path"

    def __init__(self, sendchecker, writer):
        self.sendchecker = sendchecker
        self.writer = writer
        self._stop = False       # Gets set to True to stop communications

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop

    def shutdown(self):
        self._stop = True

    async def run_tx(self, writerque):
        """Gets data from writerque, and transmits it out on the port writer"""
        while not self._stop:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit
            quexit, txdata = await queueget(writerque)
            if quexit:
                continue
            writerque.task_done()
            if txdata is None:
                continue
            if not self.sendchecker.allowed(txdata):
                # this data should not be transmitted, discard it
                continue
            # this data can be transmitted
            binarydata = ET.tostring(txdata)
            # Send to the port
            self.writer.write(binarydata)
            await self.writer.drain()
        self.writer.close()
        await self.writer.wait_closed()


class Port_RX(STDIN_RX):
    """Produces xml.etree.ElementTree data from data received on the port,
       this is used by Portcomms as one half of the communications path.
       This overwrites methods of the STDIN_RX parent class."""

    def __init__(self, sendchecker, reader):
        super().__init__()
        self.sendchecker = sendchecker
        self.reader = reader


    async def run_rx(self, readerque):
        "pass xml.etree.ElementTree data to readerque"
        try:
            # get block of xml.etree.ElementTree data
            # from self._xmlinput and append it to  readerque
            while not self._stop:
                rxdata = await self._xmlinput()
                if rxdata is None:
                    return
                if rxdata.tag == "enableBLOB":
                    # set permission flags in the sendchecker object
                    self.sendchecker.setpermissions(rxdata)
                # and place rxdata into readerque
                while not self._stop:
                    try:
                        await asyncio.wait_for(readerque.put(rxdata), timeout=0.5)
                    except asyncio.TimeoutError:
                        # queue is full, continue while loop, checking stop flag
                        continue
                    # rxdata is now in readerque, break the inner while loop
                    break
        except ConnectionError:
            # re-raise this without creating a report, as it probably indicates
            # a normal connection drop
            raise
        except Exception:
            # possibly some other error, so report it
            logger.exception("Exception report from Port_RX.run_rx")
            raise


    async def _datainput(self):
        """Waits for binary string of data ending in > from the port
           Returns None if stop flags arises"""
        binarydata = b""
        while not self._stop:
            await asyncio.sleep(0)
            try:
                data = await self.reader.readuntil(separator=b'>')
            except asyncio.LimitOverrunError:
                data = await self.reader.read(n=32000)
            except asyncio.IncompleteReadError:
                binarydata = b""
                await asyncio.sleep(0.1)
                continue
            if not data:
                await asyncio.sleep(0.1)
                continue
            # data received
            if b">" in data:
                binarydata = binarydata + data
                return binarydata
            # data has content but no > found
            binarydata += data
            # could put a max value here to stop this increasing indefinetly


class Portcomms():
    """If indipydriver.comms is set to an instance of this class it is
       used to implement communications via a port"""

    def __init__(self, devices, host="localhost", port=7624):
        # devices is a dictionary of device name to device this driver owns
        self.devices = devices
        self.sendchecker = SendChecker(devices)
        self.host = host
        self.port = port
        self.connected = False

        self.rx = None
        self.tx = None
        self.server = None
        self._stop = False       # Gets set to True to stop communications

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop

    def shutdown(self):
        "Sets self.stop to True and calls shutdown on tasks"
        self._stop = True
        if not self.rx is None:
            self.rx.shutdown()
        if not self.tx is None:
            self.tx.shutdown()
        if not self.server is None:
            self.server.close()


    async def __call__(self, readerque, writerque):
        "Called from indipydriver.asyncrun() to run the communications"
        self.readerque = readerque
        self.writerque = writerque
        logger.info(f"Listening on {self.host} : {self.port}")
        self.server = await asyncio.start_server(self.handle_data, self.host, self.port)
        try:
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            # self._stop raises an unwanted CancelledError
            # propogate this only if it is not due to self._stop
            if not self._stop:
                raise

    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        if self.connected:
            # already connected, can only handle one connection
            writer.close()
            await writer.wait_closed()
            return
        self.connected = True
        addr = writer.get_extra_info('peername')
        self.rx = Port_RX(self.sendchecker, reader)
        self.tx = Port_TX(self.sendchecker, writer)
        logger.info(f"Connection received from {addr}")
        try:
            txtask = asyncio.create_task(self.tx.run_tx(self.writerque))
            rxtask = asyncio.create_task(self.rx.run_rx(self.readerque))
            await asyncio.gather(txtask, rxtask)
        except ConnectionError:
            pass
        finally:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()
        cleanque(self.writerque)
        logger.info(f"Connection from {addr} closed")
        while True:
            if txtask.done() and rxtask.done():
                break
            await asyncio.sleep(1)


def cleanque(que):
    "Clears out a que"
    try:
        while True:
            xmldata = que.get_nowait()
            que.task_done()
    except asyncio.QueueEmpty:
        # que is now empty, nothing further to do
        pass


# Command to control whether setBLOBs should be sent to this channel from a given Device. They can
# be turned off completely by setting Never (the default), allowed to be intermixed with other INDI
# commands by setting Also or made the only command by setting Only.

# <!ELEMENT enableBLOB %BLOBenable >
# <!ATTLIST enableBLOB
# device %nameValue; #REQUIRED  name of Device
# name %nameValue; #IMPLIED name of BLOB Property, or all if absent
# >



class SendChecker:
    """Carries the enableBLOB status on a device, and does checks
       to ensure valid data is being transmitted"""

    def __init__(self, devices):
        "For every device create a dictionary"
        self.devices = devices
        self.devicestatus = {}
        # create a dictionary of devicenames :
        for devicename in devices:
            self.devicestatus[devicename] = {"Default":"Never", "Properties":{}}
            # The Properties value is a dictionary of propertyname:status

    def allowed(self, xmldata):
        "Return True if this xmldata can be transmitted, False otherwise"

        if xmldata.tag in ("getProperties", "defBLOBVector"):
            return True

        if xmldata.tag not in ("setBLOBVector", 'newBLOBVector'):
            # so anything other than a BLOB
            if self.rxonly():
                # Only blobs allowed
                return False
            return True

        # so following checks only apply to BLOB vectors

        devicename = xmldata.get("device")
        devicedict = self.devicestatus[devicename]

        # so we have a devicename, get propertyname
        name = xmldata.get("name")

        # so we have a devicename, property name,
        if name and (name in devicedict["Properties"]):
            if devicedict["Properties"][name] == "Never":
                return False
            else:
                return True
        elif devicedict["Default"] == "Never":
            return False
        else:
            return True


    def setpermissions(self, rxdata):
        "Read the received enableBLOB xml and set permission in self.devicestatus"
        devicename = rxdata.get("device")
        if devicename is None:
            # invalid
            return
        if devicename not in self.devicestatus:
            # devicename not recognised
            return

        # get the status of Never, Also, Only
        status = rxdata.text.strip()
        if status not in ("Never", "Also", "Only"):
            # invalid
            return

        devicedict = self.devicestatus[devicename]

        # property name
        name = rxdata.get("name")
        if name is None:
            # This applies to the device rather than to a particular property
            devicedict["Default"] = status
            return

        if name in devicedict["Properties"]:
            devicedict["Properties"][name] = status
            return

        # So this applies to a property that is not in self.devicestatus
        # check property is known, and add it
        if devicename in self.devices:
            if name in self.devices[devicename]:
                propertyobject = self.devices[devicename][name]
            else:
                # devicename is in self.devices, but property not found
                return

        # confirm propertyobject is a BLOBVector
        if propertyobject.vectortype != "BLOBVector":
            return

        # add it to devicedict, and hence to self.devicestatus
        devicedict["Properties"][name] = status


    def rxonly(self):
        "Returns True if any device or property has been set to BLOBs only"
        for devicedict in self.devicestatus.values():
            if devicedict["Default"] == "Only":
                return True
            properties = devicedict["Properties"]
            for status in properties.values():
                if status == "Only":
                    return True
        return False
