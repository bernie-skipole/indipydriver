

import asyncio, logging

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

from .ipydriver import IPyDriver

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

        # traffic is transmitted out on the serverwriterque
        self.serverwriterque = asyncio.Queue(6)
        # and read in from the serverreaderque
        self.serverreaderque = asyncio.Queue(6)

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
            if driver.comms is not None:
                 raise RuntimeError("A driver communications method has already been set, there can only be one")
            for devicename in driver:
                if devicename in self.devices:
                    # duplicate devicename
                    raise ValueError(f"Device name {devicename} is duplicated in the attached drivers.")
            self.devices.update(driver.data)

        self.connectionpool = []
        for connection_id in range(0, maxconnections):
            self.connectionpool.append(_ClientConnection(connection_id, self.serverreaderque))

        # This alldrivers list will have exdrivers added to it, so the list
        # here is initially a copy of self.drivers
        self.alldrivers = self.drivers.copy()

        for driver in self.drivers:
            # an instance of _DriverComms is created for each driver
            # each _DriverComms object has lists of drivers and remotes
            # these will be used to send snooping traffic

            driver.comms = _DriverComms(driver,
                                        self.serverwriterque,
                                        self.connectionpool,
                                        self.alldrivers,
                                        self.remotes)
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

    async def _queueput(self, queue, value, timeout=0.5):
        while not self._stop:
            try:
                await asyncio.wait_for(queue.put(value), timeout)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            break

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
                                   debug_enable = debug_enable,
                                   alldrivers = self.alldrivers,
                                   remotes = self.remotes,
                                   serverwriterque = self.serverwriterque,
                                   connectionpool = self.connectionpool )

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
        # add this exdriver to alldrivers
        self.alldrivers.append(exd)
        # Create a DriverComms object
        exd.comms = _DriverComms(exd,
                                 self.serverwriterque,
                                 self.connectionpool,
                                 self.alldrivers,
                                 self.remotes)
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

        for clientconnection in self.connectionpool:
            if not clientconnection.connected:
                # this clientconnection is available
                await clientconnection.handle_data(reader, writer)
                break
        else:
            # no clientconnection is available
            writer.close()
            await writer.wait_closed()


    async def asyncrun(self):
        """await this to operate the server together with its
           drivers and any remote connections."""

        # Note this gather has return_exceptions=True, so exceptions do not stop or cancel
        # other tasks from running, or stop the running loop.
        # This requires each coroutine in this gather to call shutdown on the server if any exception
        # occurs in the coroutine

        self._stop = False
        driverruns = [ self._runners(driver) for driver in self.drivers ]
        remoteruns = [ self._runners(remoteconnection) for remoteconnection in self.remotes ]
        externalruns = [ self._runners(exd) for exd in self.exdrivers ]
        try:
            await asyncio.gather(*driverruns,
                                 *remoteruns,
                                 *externalruns,
                                 self._runserver(),
                                 self._copyfromserver(),
                                 self._sendtoclient(),
                                 return_exceptions=True
                                 )
        finally:
            self.stopped.set()
            self._stop = True


    async def _runners(self, itemtorun):
        """Used by above to run drivers, remotes and externals
           If any shuts down, then calls shutdown the server"""
        try:
            await itemtorun.asyncrun()
        finally:
            self.shutdown()


    async def _copyfromserver(self):
        """Gets data from serverreaderque.
           For every driver, copy data, if applicable, to driver.readerque
           And for every remote connection if applicable, to its send method"""
        try:
            while not self._stop:
                try:
                    quedata = await asyncio.wait_for(self.serverreaderque.get(), 0.5)
                except asyncio.TimeoutError:
                    continue
                self.serverreaderque.task_done()
                connection_id, xmldata = quedata
                devicename = xmldata.get("device")
                propertyname = xmldata.get("name")

                if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
                    binarydata = ET.tostring(xmldata)
                    logger.debug(f"RX:: {binarydata.decode('utf-8')}")

                exdriverfound = False
                if (xmldata.tag in NEWTAGS) or (xmldata.tag == "getProperties"):
                    # if targetted at a known device, send it to that device
                    if devicename:
                        if devicename in self.devices:
                            # this new or getProperties request is meant for an attached device
                            await self._queueput(self.devices[devicename].driver.readerque, xmldata)
                            # no need to transmit this anywhere else, continue the while loop
                            continue
                        for exd in self.exdrivers:
                            if devicename in exd:
                                # this getProperties request is meant for an external driver
                                await self._queueput(exd.readerque, xmldata)
                                exdriverfound = True
                                break

                if exdriverfound:
                    # no need to transmit this anywhere else, continue the while loop
                    continue

                # copy to all server connections, apart from the one it came in on
                for clientconnection in self.connectionpool:
                    if clientconnection.connected and clientconnection.connection_id != connection_id:
                        await self._queueput(clientconnection.txque, xmldata)

                # copy to all remote connections
                if xmldata.tag != "enableBLOB":
                    for remcon in self.remotes:
                        if not remcon.connected:
                            continue
                        await remcon.send(xmldata)


                # transmit xmldata out to exdrivers,
                if xmldata.tag != "enableBLOB":
                    # enableBLOB instructions are not forwarded to external drivers
                    for driver in self.exdrivers:
                        if xmldata.tag == "getProperties":
                            # either no devicename, or an unknown device
                            await self._queueput(driver.readerque, xmldata)
                        elif xmldata.tag not in NEWTAGS:
                            # either devicename is unknown, or this data is to/from another driver.
                            # So check if this driver is snooping on this device/vector
                            # only forward def's and set's, not 'new' vectors which
                            # do not come from a device, but only from a client to the target device.
                            if driver.snoopall:
                                await self._queueput(driver.readerque, xmldata)
                            elif devicename and (devicename in driver.snoopdevices):
                                await self._queueput(driver.readerque, xmldata)
                            elif devicename and propertyname and ((devicename, propertyname) in driver.snoopvectors):
                                await self._queueput(driver.readerque, xmldata)


                # transmit xmldata out to drivers
                for driver in self.drivers:
                    if xmldata.tag == "getProperties":
                        # either no devicename, or an unknown device
                        await self._queueput(driver.readerque, xmldata)
                    elif xmldata.tag not in NEWTAGS:
                        # either devicename is unknown, or this data is to/from another driver.
                        # So check if this driver is snooping on this device/vector
                        # only forward def's and set's, not 'new' vectors which
                        # do not come from a device, but only from a client to the target device.
                        if driver.snoopall:
                            await self._queueput(driver.readerque, xmldata)
                        elif devicename and (devicename in driver.snoopdevices):
                            await self._queueput(driver.readerque, xmldata)
                        elif devicename and propertyname and ((devicename, propertyname) in driver.snoopvectors):
                            await self._queueput(driver.readerque, xmldata)

                # now every driver/remcon which needs it has this xmldata
                # and the while loop now continues

        finally:
            self.shutdown()

    async def _sendtoclient(self):
        "For every clientconnection, get txque and copy data into it from serverwriterque"
        try:
            while not self._stop:
                try:
                    xmldata = await asyncio.wait_for(self.serverwriterque.get(), 0.5)
                except asyncio.TimeoutError:
                    continue
                self.serverwriterque.task_done()
                #  This xmldata of None is an indication to shut the server down
                #  It is set to None when a duplicate devicename is discovered
                if xmldata is None:
                    logger.error("A duplicate devicename has caused a server shutdown")
                    return
                if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
                    binarydata = ET.tostring(xmldata)
                    logger.debug(f"TX:: {binarydata.decode('utf-8')}")
                for clientconnection in self.connectionpool:
                    if clientconnection.connected:
                        await self._queueput(clientconnection.txque, xmldata)
                # The while loop continues
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
        for clientconnection in self.connectionpool:
            if clientconnection.connected:
                # at least one is connected, so this data is put into
                # serverwriterque, and is then sent to each client by
                # the _sendtoclient method.
                await self._queueput(self.serverwriterque, xmldata)
                break

        for remcon in self.remotes:
            if not remcon.connected:
                continue
            await remcon.send(xmldata)


class _DriverComms:

    """An instance of this is created for each driver, which calls the __call__
       method.  Any data the driver wishes to be send will be taken
       from the drivers writerque and transmitted to the client by placing it
       into the serverwriterque"""

    def __init__(self, driver, serverwriterque, connectionpool, alldrivers, remotes):

        # This object is attached to this driver
        self.driver = driver
        self.serverwriterque = serverwriterque
        # connectionpool is a list of ClientConnection objects, which is used
        # to test if a client is connected
        self.connectionpool = connectionpool
        # self.connected is read by the driver, and in this case is always True
        # as the driver is connected to IPyServer, which handles snooping traffic,
        # even if no client is connected
        self.connected = True
        # self.alldrivers is set to a list of drivers, including exdrivers
        self.alldrivers = alldrivers
        # self.remotes is a list of connections to remote servers
        self.remotes = remotes
        self._stop = False       # Gets set to True to stop communications

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop the driver"
        return self._stop

    def shutdown(self):
        "Sets self.stop to True and calls shutdown on tasks"
        self._stop = True

    async def _queueput(self, queue, value, timeout=0.5):
        while not self._stop:
            try:
                await asyncio.wait_for(queue.put(value), timeout)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            break

    async def __call__(self, readerque, writerque):
        """Called by the driver, should run continuously.
           reads writerque from the driver, and sends xml data to the network"""
        while not self._stop:
            try:
                xmldata = await asyncio.wait_for(writerque.get(), 0.5)
            except asyncio.TimeoutError:
                continue
            writerque.task_done()
            # Check if other drivers/remotes wants to snoop this traffic
            devicename = xmldata.get("device")
            propertyname = xmldata.get("name")

            if xmldata.tag in NEWTAGS:
                # drivers should never transmit a new
                # but just in case
                logger.error(f"Driver transmitted invalid tag {xmldata.tag}")
                continue

            if xmldata.tag.startswith("def"):
                # check for duplicate devicename
                for driver in self.alldrivers:
                    if driver is self.driver:
                        continue
                    if devicename in driver:
                        logger.error(f"A duplicate devicename {devicename} has been detected")
                        await self._queueput(self.serverwriterque, None)
                        return
                for remote in self.remotes:
                    if devicename in remote.devicenames:
                        logger.error(f"A duplicate devicename {devicename} has been detected")
                        await self._queueput(self.serverwriterque, None)
                        return


            # check for a getProperties
            if xmldata.tag == "getProperties":
                foundflag = False
                # if getproperties is targetted at a known device, send it to that device
                if devicename:
                    for driver in self.alldrivers:
                        if driver is self.driver:
                            # No need to check sending a getProperties to itself
                            continue
                        if devicename in driver:
                            # this getProperties request is meant for an attached driver/device
                            await self._queueput(driver.readerque, xmldata)
                            foundflag = True
                            break
                    if foundflag:
                        # no need to transmit this anywhere else, continue the while loop
                        continue


            # transmit xmldata out to other drivers
            for driver in self.alldrivers:
                if driver is self.driver:
                    continue
                if xmldata.tag == "getProperties":
                    # either no devicename, or an unknown device
                    await self._queueput(driver.readerque, xmldata)
                else:
                    # Check if this driver is snooping on this device/vector
                    if driver.snoopall:
                        await self._queueput(driver.readerque, xmldata)
                    elif devicename and (devicename in driver.snoopdevices):
                        await self._queueput(driver.readerque, xmldata)
                    elif devicename and propertyname and ((devicename, propertyname) in driver.snoopvectors):
                        await self._queueput(driver.readerque, xmldata)


            for remcon in self.remotes:
                if not remcon.connected:
                    continue
                # send to all remotes
                await remcon.send(xmldata)

            for clientconnection in self.connectionpool:
                if clientconnection.connected:
                    # at least one is connected, so this data is put into
                    # serverwriterque, and is then sent to each client
                    await self._queueput(self.serverwriterque, xmldata)
                    break




class _ClientConnection:

    "Handles a client connection"

    def __init__(self, connection_id, serverreaderque):

        # number identifying this connection
        self.connection_id = connection_id

        # self.txque will have data to be transmitted
        # inserted into it from the IPyServer._sendtoclient()
        # method
        self.txque = asyncio.Queue(6)

        self.serverreaderque = serverreaderque
        # self.connected is True if this pool object is running a connection
        self.connected = False

        self.rx = None
        self.tx = None

        self._stop = False       # Gets set to True to stop communications

    @property
    def stop(self):
        "returns self._stop"
        return self._stop

    def shutdown(self):
        "Sets self.stop to True and calls shutdown on tasks"
        self._stop = True
        self.connected = False
        if self.rx is not None:
            self.rx.shutdown()
        if self.tx is not None:
            self.tx.shutdown()

    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        self.connected = True
        sendchecker = SendChecker()
        addr = writer.get_extra_info('peername')
        self.rx = Conn_RX(self.connection_id, sendchecker, reader)
        self.tx = Conn_TX(sendchecker, writer)
        logger.info(f"Connection received from {addr}")
        try:
            txtask = asyncio.create_task(self.tx.run_tx(self.txque))
            rxtask = asyncio.create_task(self.rx.run_rx(self.serverreaderque))
            await asyncio.gather(txtask, rxtask)
        except ConnectionError:
            pass
        finally:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()
        cleanque(self.txque)
        logger.info(f"Connection from {addr} closed")
        while True:
            if txtask.done() and rxtask.done():
                break
            await asyncio.sleep(1)



class Conn_TX():
    "An object that transmits data on a port"

    def __init__(self, sendchecker, writer):
        self.sendchecker = sendchecker
        self.writer = writer
        self._stop = False       # Gets set to True to stop communications

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop"
        return self._stop

    def shutdown(self):
        self._stop = True

    async def run_tx(self, writerque):
        """Gets data from writerque, and transmits it out on the port writer"""
        while not self._stop:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit
            try:
                txdata = await asyncio.wait_for(writerque.get(), 0.5)
            except asyncio.TimeoutError:
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




class Conn_RX():
    """Produces xml.etree.ElementTree data from data received on the port"""

    def __init__(self, connection_id, sendchecker, reader):
        self._remainder = b""    # Used to store intermediate data
        self._stop = False       # Gets set to True to stop communications
        self.sendchecker = sendchecker
        self.reader = reader
        self.connection_id = connection_id

    def shutdown(self):
        self._stop = True

    @property
    def stop(self):
        "returns self._stop, being the instruction to stop"
        return self._stop

    async def run_rx(self, serverreaderque):
        "pass xml.etree.ElementTree data to serverreaderque"
        try:
            # get block of xml.etree.ElementTree data
            # from self._xmlinput and append it to  serverreaderque together with connection_id
            while not self._stop:
                rxdata = await self._xmlinput()
                if rxdata is None:
                    return
                if rxdata.tag == "enableBLOB":
                    # set permission flags in the sendchecker object
                    self.sendchecker.setpermissions(rxdata)
                # and place rxdata into serverreaderque
                while not self._stop:
                    try:
                        await asyncio.wait_for(serverreaderque.put((self.connection_id, rxdata)), timeout=0.5)
                    except asyncio.TimeoutError:
                        # queue is full, continue while loop, checking stop flag
                        continue
                    # rxdata is now in serverreaderque, break the inner while loop
                    break
        except ConnectionError:
            # re-raise this without creating a report, as it probably indicates
            # a normal connection drop
            raise
        except Exception:
            # possibly some other error, so report it
            logger.exception("Exception report from Conn_RX.run_rx")
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
