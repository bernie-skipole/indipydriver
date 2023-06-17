
import asyncio, sys, os

import xml.etree.ElementTree as ET

import fcntl

from datetime import datetime


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



class STDOUT_TX:
    "An object that transmits data on stdout, used by STDINOUT as one half of the communications path"

    async def run_tx(self, writerque):
        """Gets data from writerque, and transmits it out on stdout"""
        while True:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit down stdout
            txdata = await writerque.get()
            # and send it out on stdout
            binarydata = ET.tostring(txdata)
            binarydata += b"\n"
            sys.stdout.buffer.write(binarydata)
            sys.stdout.buffer.flush()
            writerque.task_done()

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
            root = await anext(source)
            if root is not None:
                await readerque.put(root)

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


# useful test strings
# <getProperties version="1.7" />
# <newNumberVector device="Thermostat" name="targetvector"><oneNumber name="target">40</oneNumber></newNumberVector>
# sys.stderr.write((binarydata+b'\n').decode("ascii"))   - note, the + b'\n' is necessary to send this text.
# telnet localhost 7624


class STDINOUT():
    """If indipydriver.comms is set to an instance of this class it is
       used to implement communications via stdin and stdout"""

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

    def __init__(self, writer):
        self.writer = writer

    async def run_tx(self, writerque):
        """gets data from writerque, and transmits it"""
        while True:
            await asyncio.sleep(0)
            txdata = await writerque.get()
            binarydata = ET.tostring(txdata)
            # Send the next message to the port
            self.writer.write(binarydata)
            await self.writer.drain()
            writerque.task_done()



class Port_RX(STDIN_RX):
    """Produces xml.etree.ElementTree data from data received on the port,
       this is used by Portcomms as one half of the communications path.
       This overwrites the datainput method of the STDIN_RX parent class."""

    def __init__(self, reader):
        self.reader = reader

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


class Portcomms():
    """If indipydriver.comms is set to an instance of this class it is
       used to implement communications via a port"""

    def __init__(self, host="localhost", port=7624):
        self.host = host
        self.port = port
        self.connected = False

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

    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        if self.connected:
            # already connected, can only handle one connection
            writer.close()
            await writer.wait_closed()
            return
        self.connected = True
        rx = Port_RX(reader)
        tx = Port_TX(writer)
        try:
            txtask = asyncio.create_task(tx.run_tx(self.writerque))
            rxtask = asyncio.create_task(rx.run_rx(self.readerque))
            await txtask
            await rxtask
        except ConnectionResetError:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()
