
import asyncio

import xml.etree.ElementTree as ET


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


class ExVector:

    def __init__(self, name, deftag):
        "Object which only holds a name and vectortype"
        self.name = name
        self.vectortype = deftag[3:]


class ExDriver:

    def __init__(self, program, *args):

        # traffic is transmitted out from the driver on the writerque
        self.writerque = asyncio.Queue(4)
        # and read in from the readerque
        self.readerque = asyncio.Queue(4)
        self.program = program
        self.args = args
        self.proc = None

        # An object for communicating can be set
        self.comms = None

        # This dictionary will be populated with devicename:{vectorname:vector}
        # where vector is an ExVector object
        self.devicenames = {}

        self.snoopall = False           # gets set to True if it is snooping everything
        self.snoopdevices = set()       # gets set to a set of device names
        self.snoopvectors = set()       # gets set to a set of (devicename,vectorname) tuples


    def __contains__(self, item):
        "So a devicename can easily be checked if it is in this driver"
        return item in self.devicenames


    async def run_rx(self):
        "Get data from readerque and write into the driver"
        # wait for external program to start
        asyncio.sleep(0.1)
        # send a getProperties into the driver
        xldata = ET.fromstring("""<getProperties version="1.7" />""")
        await self.readerque.put(xldata)
        while True:
            await asyncio.sleep(0)
            # get block of data from readerque
            rxdata = await self.readerque.get()
            self.readerque.task_done()
            binarydata = ET.tostring(rxdata)
            binarydata += b"\n"
            self.proc.stdin.write(binarydata)
            await self.proc.stdin.drain()

    async def run_tx(self):
        "Get data from driver and pass into writerque towards the server"
        source = self.datasource()
        async for txdata in source:
            # get block of xml.etree.ElementTree data
            devicename = txdata.get("device")
            if devicename and txdata.tag in DEFTAGS:
                # its a definition
                if not (devicename in self.devicenames):
                    self.devicenames[devicename] = {}
                vectorname = txdata.get("name")
                if vectorname:
                    if not vectorname in self.devicenames[devicename]:
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
            # append it to  writerque
            await self.writerque.put(txdata)


    async def datasource(self):
        # get received data, parse it, and yield it as xml.etree.ElementTree object
        data_in = self.datainput()
        message = b''
        messagetagnumber = None
        async for data in data_in:
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
        """Generator producing binary string of data from exdriver proc
           this yields blocks of data whenever a ">" character is received."""
        data = b""
        while True:
            await asyncio.sleep(0)
            indata = await self.proc.stdout.read(100)
            if indata is None:
                await asyncio.sleep(0.02)
                continue
            data = data + indata
            while b">" in data:
                await asyncio.sleep(0)
                binarydata, data = data.split(b'>', maxsplit=1)
                binarydata += b">"
                yield binarydata


    async def asyncrun(self):
        "Runs the external driver"

        self.proc = await asyncio.create_subprocess_exec(self.program,
                                                         *self.args,
                                                   stdin=asyncio.subprocess.PIPE,
                                                   stdout=asyncio.subprocess.PIPE,
                                                   stderr=asyncio.subprocess.PIPE)

        await asyncio.gather(self.comms(self.readerque, self.writerque),
                             self.run_rx(),
                             self.run_tx())
