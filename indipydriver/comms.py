
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


def cleanque(que):
    "Clears out a que"
    try:
        while True:
            xmldata = que.get_nowait()
            que.task_done()
    except asyncio.QueueEmpty:
        # que is now empty, nothing further to do
        pass


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
