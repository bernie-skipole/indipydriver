
import asyncio, sys, os, time

import xml.etree.ElementTree as ET

import fcntl

from base64 import standard_b64encode


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


def blob_xml_bytes(xmldata):
    """A generator yielding blob xml byte strings
       for a setBLOBVector.
       reads member bytes, b64 encodes the data
       and yields the byte string including tags."""

    # yield initial setBLOBVector
    setblobvector = _makestart(xmldata)
    yield setblobvector.encode()
    for oneblob in xmldata.iter('oneBLOB'):
        bytescontent = oneblob.text
        size = oneblob.get("size")
        if size == "0":
            oneblob.set("size", str(len(bytescontent)))
        # yield start of oneblob
        start = _makestart(oneblob)
        yield start.encode()
        # yield body, b64 encoded, in chunks
        encoded_data = standard_b64encode(bytescontent)
        chunksize = 1000
        for b in range(0, len(encoded_data), chunksize):
            yield encoded_data[b:b+chunksize]
        yield b"</oneBLOB>"
    yield b"</setBLOBVector>\n"


class STDOUT_TX:
    "An object that transmits data on stdout, used by STDINOUT as one half of the communications path"

    async def run_tx(self, writerque):
        """Gets data from writerque, and transmits it out on stdout"""
        while True:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit down stdout
            txdata = await writerque.get()
            writerque.task_done()
            if (txdata.tag == "setBLOBVector") and len(txdata):
                # txdata is a setBLOBVector containing blobs
                # the generator blob_xml_bytes yields bytes
                for binarydata in blob_xml_bytes(txdata):
                    # transmit the data
                    sys.stdout.buffer.write(binarydata)
                    sys.stdout.buffer.flush()
                    await asyncio.sleep(0)
            else:
                # its straight xml, send it out on stdout
                binarydata = ET.tostring(txdata)
                binarydata += b"\n"
                sys.stdout.buffer.write(binarydata)
                sys.stdout.buffer.flush()


class STDIN_RX:
    """An object that receives data, parses it to ElementTree elements
       and passes it to the driver by appending it to the driver's readerque"""

    async def run_rx(self, readerque):
        "pass data to readerque"
        source = self.datasource()
        while True:
            await asyncio.sleep(0)
            if readerque is None:
                continue
            # get block of xml.etree.ElementTree data
            # from source and append it to  readerque
            rxdata = await anext(source)
            if rxdata is not None:
                await readerque.put(rxdata)

    async def datasource(self):
        # get received data, parse it, and yield it as xml.etree.ElementTree object
        data_in = self.datainput()
        message = b''
        messagetagnumber = None
        while True:
            await asyncio.sleep(0)
            # get blocks of data from stdin
            data = await anext(data_in)
            if not data:
                continue
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
                        message = b''
                        messagetagnumber = None
                        continue
                    # xml datablock done, yield it up
                    yield root
                    # and start again, waiting for a new message
                    message = b''
                    messagetagnumber = None
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
                    message = b''
                    messagetagnumber = None
                    continue
                # xml datablock done, yield it up
                yield root
                # and start again, waiting for a new message
                message = b''
                messagetagnumber = None

    async def datainput(self):
        """Generator producing binary string of data from stdin
           this yields blocks of data whenever a ">" character is received."""
        data = b""
        while True:
            await asyncio.sleep(0)
            indata = sys.stdin.buffer.read(100)
            if indata is None:
                continue
            data = data + indata
            while b">" in data:
                await asyncio.sleep(0)
                binarydata, data = data.split(b'>', maxsplit=1)
                binarydata += b">"
                yield binarydata


class STDINOUT():
    """If indipydriver.comms is set to an instance of this class it is
       used to implement communications via stdin and stdout"""

    def __init__(self):
        self.connected = True


    async def __call__(self, readerque, writerque):
        "Called from indipydriver.asyncrun() to run the communications"
        # Set stdin to non-blocking mode
        flags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
        fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)

        rx = STDIN_RX()
        tx = STDOUT_TX()

        await asyncio.gather(rx.run_rx(readerque),
                             tx.run_tx(writerque)
                             )

class Port_TX():
    "An object that transmits data on a port, used by Portcomms as one half of the communications path"

    def __init__(self, blobstatus, writer, timer):
        self.blobstatus = blobstatus
        self.writer = writer
        self.timer = timer


    async def run_tx(self, writerque):
        """Gets data from writerque, and transmits it out on the port writer"""
        while True:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit
            txdata = await writerque.get()
            writerque.task_done()
            if len(txdata) and not self.blobstatus.allowed(txdata):
                # this data should not be transmitted, discard it
                # however if the vector has no content, but perhaps just message and state
                # still allow it
                continue
            # this data can be transmitted
            if txdata.tag == "setBLOBVector" and len(txdata):
                # txdata is a setBLOBVector containing blobs
                # the generator blob_xml_bytes yields bytes
                for binarydata in blob_xml_bytes(txdata):
                    # Send to the port
                    self.timer.update()
                    self.writer.write(binarydata)
                    await self.writer.drain()
            else:
                # its straight xml, send it out on the port
                binarydata = ET.tostring(txdata)
                # Send to the port
                self.timer.update()
                self.writer.write(binarydata)
                await self.writer.drain()


class Port_RX(STDIN_RX):
    """Produces xml.etree.ElementTree data from data received on the port,
       this is used by Portcomms as one half of the communications path.
       This overwrites methods of the STDIN_RX parent class."""

    def __init__(self, blobstatus, reader):
        self.blobstatus = blobstatus
        self.reader = reader

    async def run_rx(self, readerque):
        "pass data to readerque"
        source = self.datasource()
        while True:
            await asyncio.sleep(0)
            if readerque is None:
                continue
            # get block of xml.etree.ElementTree data
            # from source and append it to  readerque
            rxdata = await anext(source)
            if rxdata is not None:
                if rxdata.tag == "enableBLOB":
                    # set permission flags in the blobstatus object
                    self.blobstatus.setpermissions(rxdata)
                # and place rxdata into readerque
                await readerque.put(rxdata)


    async def datainput(self):
        "Generator producing binary string of data from the port"
        binarydata = b""
        while True:
            await asyncio.sleep(0)
            try:
                data = await self.reader.readuntil(separator=b'>')
            except asyncio.LimitOverrunError:
                data = await self.reader.read(n=32000)
            except Exception:
                binarydata = b""
                continue
            if not data:
                continue
            if b">" in data:
                binarydata = binarydata + data
                yield binarydata
                binarydata = b""
            else:
                # data has content but no > found
                binarydata += data
                # could put a max value here to stop this increasing indefinetly


class TXTimer():

    def __init__(self, timeout = 15):
        self.timer = time.time()
        self.timeout = timeout

    def update(self):
        "call this every time a transmission is made, and it resets the timer"
        self.timer = time.time()

    def elapsed(self):
        "Return True if more than timeout seconds have elapsed since last update"
        telapsed = time.time() - self.timer
        if telapsed > self.timeout:
            self.timer = time.time()
            return True
        return False


class Portcomms():
    """If indipydriver.comms is set to an instance of this class it is
       used to implement communications via a port"""

    def __init__(self, devices, host="localhost", port=7624):
        # devices is a dictionary of device name to device this driver owns
        self.devices = devices
        self.blobstatus = BLOBSstatus(devices)
        self.host = host
        self.port = port
        self.connected = False

        # timer used to force a data transmission after timeout seconds
        # this will cause an exception if the connection is broken and will shut down
        # the connection
        self.timer = TXTimer(timeout = 15)

    async def __call__(self, readerque, writerque):
        "Called from indipydriver.asyncrun() to run the communications"
        self.readerque = readerque
        self.writerque = writerque
        server = await asyncio.start_server(self.handle_data, self.host, self.port)
        try:
            await server.serve_forever()
        except KeyboardInterrupt as e:
            server.close()
            raise e


    async def _monitor_connection(self):
        """If connected and not transmitting, send def vectors every self.timeout seconds
           This ensures that if the connection has failed, due to the client disconnecting, the write
           to the port operation will cause a failure exception which will close the connection"""
        while True:
            await asyncio.sleep(5)
            # this is tested every five seconds
            if self.connected and self.writerque.empty() and self.readerque.empty():
                # only need to test if the queue are empty
                if self.timer.elapsed():
                    # no transmission in timeout seconds so send defVectors
                    for device in self.devices.values():
                        for vector in device.values():
                            await vector.send_defVector()


    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        if self.connected:
            # already connected, can only handle one connection
            writer.close()
            await writer.wait_closed()
            return
        self.connected = True
        rx = Port_RX(self.blobstatus, reader)
        tx = Port_TX(self.blobstatus, writer, self.timer)
        try:
            txtask = asyncio.create_task(tx.run_tx(self.writerque))
            rxtask = asyncio.create_task(rx.run_rx(self.readerque))
            montask = asyncio.create_task(self._monitor_connection())
            await asyncio.gather(txtask, rxtask, montask)
        except Exception as e:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()
            montask.cancel()
            cleanque(self.writerque)


def cleanque(que):
    "Clears out a que"
    try:
        while True:
            xmldata = que.get_nowait()
            que.task_done()
    except asyncio.QueueEmpty:
        # que is now empty, nothing further to do
        pass


class BLOBSstatus:
    "Carries the enableBLOB status on a device or property"

    def __init__(self, devices):
        "For every device, propertyvector create a status list of (Other allowed, BLOB allowed)"
        self.devicestatus = {}
        # create a dictionary of devicenames : list of propertynames for that device
        self.deviceproperties = {}
        for devicename, device in devices.items():
            self.deviceproperties[devicename] = []
            for propertyvector in device.values():
                # Initially set with BLOBs not allowed
                self.devicestatus[(devicename, propertyvector.name)] = (True, False)
                self.deviceproperties[devicename].append(propertyvector.name)


    def allowed(self, xmldata):
        "Return True if this xmldata can be transmitted, False otherwise"
        devicename = xmldata.get("device")
        if devicename is None:
            # either a getproperties or message, only deny it if ALL Other allowed are False
            # so this connection is dedictated to BLOBs only
            for status in self.devicestatus.values():
                if status[0]:
                    return True
            return False
        if not (devicename in self.deviceproperties):
            # devicename not recognised
            return False
        # so we have a devicename, get propertyname
        name = xmldata.get("name")
        # if name missing, could be a message, cannot be a setBLOBVector
        if name is None:
            # only deny it if ALL other allowed are False for this device
            properties = self.deviceproperties[devicename]
            for name in properties:
                status = self.devicestatus[devicename, name]
                if status[0]:
                    return True
            return False
        # so we have a devicename, propertyname
        status = self.devicestatus.get((devicename, name))
        if status is None:
            # this property is not recognised as belonging to the device
            return False
        if xmldata.tag == "setBLOBVector":
            return status[1]
        else:
            return status[0]


    def setpermissions(self, rxdata):
        "Read the received enableBLOB xml and set permission in self.devicestatus"

        # Command to control whether setBLOBs should be sent to this channel from a given Device. They can
        # be turned off completely by setting Never (the default), allowed to be intermixed with other INDI
        # commands by setting Also or made the only command by setting Only.

        devicename = rxdata.get("device")
        if devicename is None:
            # invalid
            return
        if not (devicename in self.deviceproperties):
            # devicename not recognised
            return
        value = rxdata.text.strip()
        if value == "Never":
            perm = (True, False)    # (Other allowed, BLOB not allowed)
        elif value == "Also":
            perm = (True, True)     # (Other allowed, BLOB allowed)
        elif value == "Only":
            perm = (False, True)   # (Only not allowed, BLOB allowed)
        else:
            # value not recognised
            return
        propertyname = rxdata.get("name")
        if propertyname is None:
            # This applies to all properties of the device
            properties = self.deviceproperties[devicename]
            for name in properties:
                self.devicestatus[devicename, name] = perm
        elif (devicename, propertyname) in self.devicestatus:
            self.devicestatus[devicename, propertyname] = perm
        # otherwise the (devicename, propertyname) are not recognised
        # so return without setting any permissions
