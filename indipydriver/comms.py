
import asyncio, sys

import xml.etree.ElementTree as ET

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
    "An object that transmits data on stdout"

    async def run_tx(self, writerque):
        """gets data from writerque, and transmits it"""
        while True:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit down stdout
            if writerque:
                txdata = writerque.popleft()
                # and send it out on stdout
                binarydata = ET.tostring(txdata)
                sys.stdout.buffer.write(binarydata)
                sys.stdout.buffer.flush()


class RX:
    """An object that receives data, parses it to ElementTree elements
       and passes it to the driver by appending it to the driver's readerque"""

    async def run_rx(self, readerque):
        "pass data to readerque"
        source = self.datasource()
        while True:
            if readerque is None:
                await asyncio.sleep(0.1)
                continue
            # get block of xml.etree.ElementTree data
            # from source and append it to  readerque
            root = await anext(source)
            if root is not None:
                readerque.append(root)

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
                except Exception:
                    message = b''
                    messagetagnumber = None
                    continue
                # xml datablock done, yield it up
                yield root
                # and start again, waiting for a new message
                message = b''
                messagetagnumber = None


    async def datainput(self):
        "Generator producing binary string of data, override in child subclass"
        while True:
            await asyncio.sleep(0)
            yield b""



class STDIN_RX(RX):
    """Produces xml.etree.ElementTree data from stdin"""

    async def datainput(self):
        "Generator producing binary string of data from stdin"
        binarydata = b""
        while True:
            await asyncio.sleep(0)
            data = sys.stdin.buffer.read(100)
            if not data:
                continue
            parts = data.split(b">")
            if len(parts) == 1:
                # no > found
                binarydata += data
                # could put a max value here to stop this increasing indefinetly
                continue
            for part in parts[:-1]:
                binarydata = binarydata + part + b">"
                yield binarydata
                binarydata = b""
            binarydata = parts[-1]


class STDINOUT():

    async def run(self, writerque, readerque):

        rx = STDIN_RX()
        tx = STDOUT_TX()

        await asyncio.gather(rx.run_rx(readerque),
                             tx.run_tx(writerque))   # run communications