
import asyncio, copy

import xml.etree.ElementTree as ET

import logging
logger = logging.getLogger(__name__)


# All xml data sent from the driver should be contained in one of the following tags
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


class ExVector:

    def __init__(self, name, deftag):
        "Object which only holds a name and vectortype"
        self.name = name
        self.vectortype = deftag[3:]


class ExDriver:

    def __init__(self, program, *args, debug_enable=False):
        "Executes a third party indi driver, communicates by stdin stdout"

        self.program = program
        self.args = args
        self.debug_enable = debug_enable
        self.proc = None

        # An object for communicating is set when this driver is added to the server
        self._commsobj = None

        # This dictionary will be populated with devicename:{vectorname:vector}
        # where vector is an ExVector object
        self.devicenames = {}

        self.snoopall = False           # gets set to True if it is snooping everything
        self.snoopdevices = set()       # gets set to a set of device names
        self.snoopvectors = set()       # gets set to a set of (devicename,vectorname) tuples

        self._remainder = b""    # Used to store intermediate data
        self._stop = False       # Gets set to True to stop communications


    def shutdown(self):
        self._stop = True
        if self._commsobj is not None:
            self._commsobj.shutdown()
        if self.proc is not None:
            self.proc.terminate()


    def __contains__(self, item):
        "So a devicename can easily be checked if it is in this driver"
        return item in self.devicenames


    async def _readdata(self, root):
        """Called from communications object with received xmldata
           and sends it towards the driver"""

        if self._stop:
            return

        if root.tag == "enableBLOB":
            return

        if root.tag == "getProperties":
            await self.xml_to_ext(root)
            return

        devicename = root.get("device")
        propertyname = root.get("name")

        if root.tag in NEWTAGS:
            if devicename is None:
                # invalid
                return
            if devicename in self.devicenames:
                await self.xml_to_ext(root)
                return
            else:
                # not for this driver
                return

        # so not in NEWTAGS
        # Check if this driver is snooping on this device/vector
        if self.snoopall:
            await self.xml_to_ext(root)
        elif devicename and (devicename in self.snoopdevices):
            await self.xml_to_ext(root)
        elif devicename and propertyname and ((devicename, propertyname) in self.snoopvectors):
            await self.xml_to_ext(root)


    async def xml_to_ext(self, root):
        "Pass data to the external driver"

        binarydata = ET.tostring(root)

        # log the received data
        if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
            logger.debug(f"RX:: {binarydata.decode('utf-8')}")

        binarydata += b"\n"
        self.proc.stdin.write(binarydata)
        await self.proc.stdin.drain()



    async def _run_tx(self):
        "Get data from driver and send it towards the server"
        try:
            # get block of xml.etree.ElementTree data
            # from self._xmlinput and append it to self.writerque
            while not self._stop:
                txdata = await self._xmlinput()
                if txdata is None:
                    return
                # get block of xml.etree.ElementTree data
                devicename = txdata.get("device")
                if devicename and txdata.tag in DEFTAGS:
                    # its a definition
                    if devicename not in self.devicenames:
                        self.devicenames[devicename] = {}
                    vectorname = txdata.get("name")
                    if vectorname:
                        if vectorname not in self.devicenames[devicename]:
                            # add this vector to the self.devicenames[devicename] dictionary
                            self.devicenames[devicename][vectorname] = ExVector(vectorname, txdata.tag)
                # check for a getProperties being sent, record what is being snooped
                if txdata.tag == "getProperties":
                    vectorname = txdata.get("name")
                    if devicename is None:
                        self.snoopall = True
                    elif vectorname is None:
                        self.snoopdevices.add(devicename)
                    else:
                        self.snoopvectors.add((devicename,vectorname))

                # transmit this data towards the server
                await self._commsobj.run_tx(txdata)

                if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
                    binarydata = ET.tostring(txdata)
                    logger.debug(f"TX:: {binarydata.decode('utf-8')}")

        except Exception:
            logger.exception("Exception report from ExDriver._run_tx")
            raise


    async def _xmlinput(self):
        """get data from driver, parse it, and return it as xml.etree.ElementTree object
           Returns None if stop flags arises"""
        message = b''
        messagetagnumber = None
        while not self._stop:
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
                    except Exception:
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
                except Exception:
                    # failed to parse the message, continue at beginning
                    message = b''
                    messagetagnumber = None
                    continue
                # xml datablock done, return it
                return root
            # so message is in progress, with a messagetagnumber set
            # but no valid endtag received yet, so continue the loop


    async def _datainput(self):
        """Waits for binary string of data ending in > from the driver
           Returns None if stop flags arises"""
        remainder = self._remainder
        if b">" in remainder:
            # This returns with binary data ending in > as long
            # as there are > characters in self._remainder
            binarydata, self._remainder = remainder.split(b'>', maxsplit=1)
            binarydata += b">"
            return binarydata
        # As soon as there are no > characters left in self._remainder
        # get more data from the driver
        while not self._stop:
            await asyncio.sleep(0)
            indata = await self.proc.stdout.read(100)
            if not indata:
                await asyncio.sleep(0.02)
                continue
            remainder += indata
            if b">" in indata:
                binarydata, self._remainder = remainder.split(b'>', maxsplit=1)
                binarydata += b">"
                return binarydata


    async def _run_err(self):
        """gets binary string of data from exdriver proc.stderr
           and logs it to logging.error."""

        while not self._stop:
            bindata = await self.proc.stderr.readline()
            if not bindata:
                await asyncio.sleep(0.02)
                continue
            logger.error(bindata.decode('utf-8'))


    async def asyncrun(self):
        "Runs the external driver"

        self._stop = False

        try:

            self.proc = await asyncio.create_subprocess_exec(self.program,
                                                             *self.args,
                                                       stdin=asyncio.subprocess.PIPE,
                                                       stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)

            # wait for external program to start
            await asyncio.sleep(0.1)
            # send a getProperties into the driver
            await self._readdata( ET.fromstring("""<getProperties version="1.7" />""") )

            async with asyncio.TaskGroup() as tg:
                tg.create_task( self._run_tx() )           # Get data from driver and send it towards the server
                tg.create_task( self._run_err() )          # data from exdriver proc.stderr and logs it to logging.error
        except Exception:
            logger.exception("Driver shutdown")
        finally:
            self._stop = True
