

import asyncio, logging

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

from .ipydriver import IPyDriver, TerminateTaskGroup, force_terminate_task_group

from .remote import RemoteConnection

from .exdriver import ExDriver

logger = logging.getLogger(__name__)


# All xml data should be contained in one of the following tags
TAGS = (b'getProperties',
        b'newTextVector',
        b'newNumberVector',
        b'newSwitchVector',
        b'newBLOBVector',
        b'enableBLOB',
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



def cleanque(que):
    "Clears out a que"
    try:
        while True:
            que.get_nowait()
            que.task_done()
    except asyncio.QueueEmpty:
        # que is now empty, nothing further to do
        pass


class IPyServer:

    """Once an instance of this class is created, the asyncrun method
       should be awaited which will open a port, and the INDI service
       will be available for clients to connect.

       drivers are IPyDriver objects this driver handles,
       host and port are "localhost" and 7624 as default

       maxconnections is the number of simultaneous client connections
       accepted, with a default of 5. The number given should be
       between 1 and 10 inclusive.

       If, prior to asyncrun being awaited, the add_remote method is called,
       then a connection will be made to a remote INDI server and any of its
       drivers.

       The add_remote method can be called multiple times to create
       connections to different servers making a branching
       tree of servers and drivers.

       The add_exdriver method can be called to run an executable driver and
       this server will communicate to it by stdin, stdout and stderr, therefore
       ipyserver can act as a general INDI server for third party drivers as
       well as ipydriver instances.
       """


    def __init__(self, *drivers, host="localhost", port=7624, maxconnections=5):

        self.drivers = list(drivers)
        self.host = host
        self.port = port

        # all data is sent on one que with format (con_id, xmldata)
        # con_id is used to stop a transmitter receiving its own transmitted data

        self.xml_data_que = asyncio.Queue(50)

        self.con_id = 0

        # If True, xmldata will be logged at DEBUG level
        self.debug_enable = True

        if maxconnections<1 or maxconnections>10:
            raise ValueError("maxconnections should be a number between 1 and 10 inclusive.")
        self.maxconnections = maxconnections

        # this is a dictionary of device name to device
        self.devices = {}

        # self.remotes is a list of RemoteConnection objects running connections to remote servers
        # this list is populated by calling self.add_remote(host, port, debug_enable)
        self.remotes = []

        # self.exdrivers is a list of ExDriver objects running external drivers
        # this list is populated by calling self.add_exdriver(program, *args, debug_enable=False)
        self.exdrivers = []

        for driver in self.drivers:
            if not isinstance(driver, IPyDriver):
                raise TypeError("The drivers set in IPyServer must all be IPyDrivers")
            for devicename in driver:
                if devicename in self.devices:
                    # duplicate devicename
                    raise ValueError(f"Device name {devicename} is duplicated in the attached drivers.")
            self.devices.update(driver.data)


        self.connectionpool = []
        for c in range(0, maxconnections):
            self.con_id += 1
            self.connectionpool.append(_ClientConnection(self.con_id, self.xml_data_que))

        for driver in self.drivers:
            # an instance of _DriverComms is created for each driver
            self.con_id += 1
            driver._commsobj = _DriverComms(driver, self.con_id, self.xml_data_que)

        # shutdown routine sets this to True to stop coroutines
        self._stop = False
        # this is set when asyncrun is finished
        self.stopped = asyncio.Event()
        self.server = None

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the server"
        return self._stop

    def shutdown(self, shutdownmessage=""):
        """Shuts down the server, sets the flag self._stop to True
           and sends shutdownmessage to logger.error if given"""
        if shutdownmessage:
            logger.error(shutdownmessage)
        self._stop = True
        for driver in self.drivers:
            driver.shutdown()
        for remcon in self.remotes:
            remcon.shutdown()
        for exd in self.exdrivers:
            exd.shutdown()
        for clientconnection in self.connectionpool:
            clientconnection.shutdown()
        if self.server is not None:
            self.server.close()
        self.stopped.set()


    def add_remote(self, host, port, blob_enable=False, debug_enable=False):
        """Adds a connection to a remote server.
           blob_enable can be True or False.
           If True BLOBs and other vectors can all be sent.
           If False, then BLOB traffic will not pass over this link.

           If debug_enable is True, then DEBUG level logging will record xml
           traffic, if False, the xml traffic will not be logged. This can be
           used to prevent multiple such connections all logging xml traffic together."""


        remcon = RemoteConnection( host=host, port=port,
                                   blob_enable = blob_enable,
                                   debug_enable = debug_enable )

        # Create a DriverComms object
        self.con_id += 1
        remcon._commsobj = _DriverComms(remcon, self.con_id, self.xml_data_que)
        # store this object
        self.remotes.append(remcon)


    def add_exdriver(self, program, *args, debug_enable=False):
        """Adds an executable driver program, runs it and communicates to it via stdin, stdout
           and stderr. Then serves the driver, and any others added, by the listening port.
           args is used for the program arguments if any.
           Any program output on stderr will be logged at level ERROR.

           If debug_enable is True, then DEBUG level logging will record xml
           traffic, if False, the xml traffic will not be logged. This can be
           used to prevent multiple drivers all logging xml traffic together."""
        exd = ExDriver(program, *args, debug_enable=debug_enable)
        # Create a DriverComms object
        self.con_id += 1
        exd._commsobj = _DriverComms(exd, self.con_id, self.xml_data_que)
        # store this object
        self.exdrivers.append(exd)



    async def _runserver(self):
        "Runs the server on the given host and port"
        logger.info(f"{self.__class__.__name__} listening on {self.host} : {self.port}")
        self.server = await asyncio.start_server(self.handle_data, self.host, self.port)
        try:
            async with self.server:
                await self.server.serve_forever()
        finally:
            self.shutdown()


    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"

        try:
            for clientconnection in self.connectionpool:
                if not clientconnection.connected:
                    # this clientconnection is available
                    await clientconnection.handle_data(reader, writer)
                    break
        except Exception:
            # Call has dropped
            logger.info("Call dropped")
        try:
            # call dropped or no clientconnection is available
            writer.close()
            await writer.wait_closed()
        except BrokenPipeError:
            # avoid broken pipe error being displayed
            pass


    async def asyncrun(self):
        """await this to operate the server together with its
           drivers and any remote connections."""

        self._stop = False

        try:
            async with asyncio.TaskGroup() as tg:
                for driver in self.drivers:
                    tg.create_task( driver.asyncrun() )
                for exdriver in self.exdrivers:
                    tg.create_task( exdriver.asyncrun() )
                for remcon in self.remotes:
                    tg.create_task( remote.asyncrun() )
                tg.create_task( self._runserver() )
                tg.create_task( self._broadcast() )
        except Exception:
            pass
        finally:
            self.shutdown()


    async def _broadcast(self):
        "Get items from the que, and broadcast to drivers"
        try:
            while not self._stop:
                try:
                    quedata = await asyncio.wait_for(self.xml_data_que.get(), 0.5)
                except asyncio.TimeoutError:
                    continue
                self.xml_data_que.task_done()
                con_id, xmldata = quedata
                async with asyncio.TaskGroup() as tg:
                    if self._stop:
                        # add an exception-raising task to force the group to terminate
                        tg.create_task(force_terminate_task_group())
                        break
                    for driver in self.drivers:
                        # send data to the drivers
                        tg.create_task( driver._commsobj.driver_rx(con_id, xmldata) )
                    for exdriver in self.exdrivers:
                        # send data to the external drivers
                        tg.create_task( exdriver._commsobj.driver_rx(con_id, xmldata) )
                    for remcon in self.remotes:
                        tg.create_task( remcon._commsobj.driver_rx(con_id, xmldata) )
                    for clientconnection in self.connectionpool:
                        # send data out to clients
                        tg.create_task( clientconnection._client_tx(con_id, xmldata) )
        finally:
            self.shutdown()


    async def send_message(self, message, timestamp=None):
        """Send system wide message, timestamp should normally not be set, if
           given, it should be a datetime.datetime object with tz set to timezone.utc"""
        if self._stop:
            return
        if not timestamp:
            timestamp = datetime.now(tz=timezone.utc).replace(tzinfo = None)
        else:
            if not isinstance(timestamp, datetime):
                # invalid timestamp given
                return
            if timestamp.tzinfo is not None:
                if timestamp.tzinfo == timezone.utc:
                    timestamp = timestamp.replace(tzinfo = None)
                else:
                    # invalid timestamp
                    return
        xmldata = ET.Element('message')
        xmldata.set("timestamp", timestamp.isoformat(sep='T'))
        xmldata.set("message", message)
        # send with a con_id of zero, so it is sent everywhere
        await self.xml_data_que.put( (0, xmldata) )


class _DriverComms:

    """An instance of this is created for each driver.  Any data the driver
       wishes to send will be transmitted via run_tx
       Any data received on self.xml_data_que will be sent to the
       driver by calling its driver.receivedata method"""

    def __init__(self, driver, con_id, xml_data_que):

        # This object is attached to this driver
        self.driver = driver
        self.con_id = con_id
        self.xml_data_que = xml_data_que


    def shutdown(self):
        "Called by driver on shutdown, used by _STDINOUT but not relevant here"
        pass


    async def run_rx(self):
        "Called by driver on running, used by _STDINOUT but not relevant here"
        pass


    async def driver_rx(self, con_id, xmldata):
        "Gets data from xml_data_que, and sends it to the driver"
        if self.con_id == con_id:
            # do not rx data this driver is transmitting
            return

        if xmldata.tag == "getProperties":
            version = xmldata.get("version")
            if version != "1.7":
                return

        # check for incoming duplicates
        if xmldata.tag in DEFTAGS:
            devicename = xmldata.get("device")
            if devicename is None:
                # invalid definition
                return
            if devicename in self.driver:
                # duplicate address
                logger.error(f"Duplicate address: Received a definition of device {devicename}")
                self.driver.shutdown()
                return

        # call the drivers receive data function
        await self.driver._readdata(xmldata)


    async def run_tx(self, xmldata):
        """Called by the driver, places data generated by the driver into xml_data_que with this connection id"""
        await self.xml_data_que.put( (self.con_id, xmldata) )


    async def run_tx_everywhere(self, xmldata):
        """Called to send data down every connection,places data generated by the driver into xml_data_que with zero connection id"""
        await self.xml_data_que.put( (0, xmldata) )




class _ClientConnection:

    "Handles a client connection"

    def __init__(self, con_id, xml_data_que):

        # number identifying this connection
        self.con_id = con_id

        self.xml_data_que = xml_data_que

        # self.connected is True if this pool object is running a connection
        self.connected = False
        self._remainder = b""    # Used to store intermediate data
        self.sendchecker = None

        self.rx = None


    def shutdown(self):
        "Shuts down the connection"
        self.connected = False

    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        self.connected = True
        self._remainder = b""    # Used to store intermediate data
        self.writer = writer
        self.reader = reader
        self.sendchecker = SendChecker()
        addr = writer.get_extra_info('peername')
        logger.info(f"Connection received from {addr} on connection {self.con_id}")
        try:
            await self._client_rx()
        except ConnectionError:
            pass
        finally:
            self.shutdown()
        logger.info(f"Connection from {addr} closed")


    async def _client_tx(self, con_id, xmldata):
        "Sends data from port to client"
        if self.con_id == con_id:
            # do not tx data this driver is receiving
            return
        if not self.connected:
            return
        if not self.sendchecker.allowed(xmldata):
            # this data should not be transmitted, discard it
            return
        try:
            # this data can be transmitted
            binarydata = ET.tostring(xmldata)
            # Send to the port
            self.writer.write(binarydata)
            await self.writer.drain()
        except ConnectionError:
            self.shutdown()



    async def _client_rx(self):
        "Receives data coming in to port from client"

        try:
            # get block of xml.etree.ElementTree data
            # from self._xmlinput and send it to xml_data_que together with connection_id
            while self.connected:
                xmldata = await self._xmlinput()
                if xmldata is None:
                    return
                if xmldata.tag == "enableBLOB":
                    # set permission flags in the sendchecker object
                    self.sendchecker.setpermissions(xmldata)
                    # do not broadcast this, so continue
                    continue
                # pass xmldata to xml_data_que
                await self.xml_data_que.put( (self.con_id, xmldata) )
        except ConnectionError:
            # re-raise this without creating a report, as it probably indicates
            # a normal connection drop
            raise
        except Exception:
            # possibly some other error, so report it
            logger.exception("Exception report from _ClientConnection._client_rx")
            raise


    async def _xmlinput(self):
        """get data from  _datainput, parse it, and return it as xml.etree.ElementTree object
           Returns None if stop flags arises"""
        message = b''
        messagetagnumber = None
        while self.connected:
            await asyncio.sleep(0)
            data = await self._datainput()
            # data is either None, or binary data ending in b">"
            if data is None:
                return
            if not self.connected:
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
        """Waits for binary string of data ending in > from the port
           Returns None if stop flags arises"""
        binarydata = b""
        while self.connected:
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



# Command to control whether setBLOBs should be sent to this channel from a given Device. They can
# be turned off completely by setting Never (the default), allowed to be intermixed with other INDI
# commands by setting Also or made the only command by setting Only.

# <!ELEMENT enableBLOB %BLOBenable >
# <!ATTLIST enableBLOB
# device %nameValue; #REQUIRED  name of Device
# name %nameValue; #IMPLIED name of BLOB Property, or all if absent
# >



class SendChecker:
    """Carries the enableBLOB status on a connection, and does checks
       to ensure valid data is being transmitted"""

    def __init__(self):
        "For every device create a dictionary"
        self.devicestatus = {}
        # create a dictionary of devicenames : to devicedict
        # where the devicedict will be {"Default":"Never", "Properties":{}}
        # The Properties value is a dictionary of propertyname:status


    def allowed(self, xmldata):
        "Return True if this xmldata can be transmitted, False otherwise"

        if xmldata.tag in ("getProperties", "delProperty"):
            return True

        if xmldata.tag not in ("defBLOBVector", "setBLOBVector", 'newBLOBVector'):
            # so anything other than a BLOB
            if self.rxonly():
                # Only blobs allowed
                return False
            return True

        # so following checks only apply to BLOB vectors

        devicename = xmldata.get("device")

        if devicename not in self.devicestatus:
            # devicename not recognised, add it
            self.devicestatus[devicename] = {"Default":"Never", "Properties":{}}

        if xmldata.tag == "defBLOBVector":
            return True

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
            # devicename not recognised, add it
            self.devicestatus[devicename] = {"Default":"Never", "Properties":{}}

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
        else:
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
