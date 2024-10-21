

import collections, asyncio, sys, copy

from datetime import datetime, timezone

import xml.etree.ElementTree as ET

from functools import partialmethod

import logging
logger = logging.getLogger(__name__)

from .ipydriver import IPyDriver

from .comms import Port_RX, Port_TX, cleanque, SendChecker, queueget

from .remote import RemoteConnection

from .exdriver import ExDriver

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
            if not driver.comms is None:
                 raise RuntimeError("A driver communications method has already been set, there can only be one")
            for devicename in driver:
                if devicename in self.devices:
                    # duplicate devicename
                    raise ValueError(f"Device name {devicename} is duplicated in the attached drivers.")
            self.devices.update(driver.data)

        self.connectionpool = []
        for clientconnection in range(0, maxconnections):
            self.connectionpool.append(_ClientConnection(self.devices, self.exdrivers, self.remotes, self.serverreaderque))

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
           and prints shutdownmessage if given"""
        if shutdownmessage:
            print(shutdownmessage)
        self._stop = True
        for driver in self.drivers:
            driver.shutdown()
        for remcon in self.remotes:
            remcon.shutdown()
        for exd in self.exdrivers:
            exd.shutdown()
        for clientconnection in self.connectionpool:
            clientconnection.shutdown()
        if not self.server is None:
            self.server.close()

    async def _queueput(self, queue, value, timeout=0.5):
        while not self._stop:
            try:
                await asyncio.wait_for(queue.put(value), timeout)
            except asyncio.TimeoutError:
                # queue is full, continue while loop, checking stop flag
                continue
            break

    def add_remote(self, host, port, blob_enable="Never", debug_enable=False):
        """Adds a connection to a remote server.
           blob_enable can be Never, Also or Only.
           If Never BLOBs will not be sent from the remote server to this one.
           If Also BLOBs and other vectors can all be sent.
           If Only, then only BLOB traffic will be sent.

           If debug_enable is True, then DEBUG level logging will record xml
           traffic, if False, the xml traffic will not be logged. This can be
           used to prevent multiple such connections all logging xml traffic together."""


        snoopall = False           # gets set to True if it is snooping everything
        snoopdevices = set()       # gets set to a set of device names
        snoopvectors = set()       # gets set to a set of (devicename,vectorname) tuples

        remcon = RemoteConnection(indihost=host, indiport=port,
                                  alldrivers = self.alldrivers,
                                  remotes = self.remotes,
                                  serverwriterque = self.serverwriterque,
                                  connectionpool = self.connectionpool,
                                  blob_enable = blob_enable,
                                  snoopall = snoopall,
                                  snoopdevices = snoopdevices,
                                  snoopvectors = snoopvectors )

        if debug_enable:
            remcon.debug_verbosity(2) # turn on xml logs
        else:
            remcon.debug_verbosity(0) # turn off xml logs
        # turn off timers, these are more appropriate to a client
        remcon.set_vector_timeouts(timeout_enable=False)
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
        except asyncio.CancelledError:
            # self._stop raises an unwanted CancelledError
            # propogate this only if it is not due to self._stop
            if not self._stop:
                raise

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
        self._stop = False
        driverruns = [ driver.asyncrun() for driver in self.drivers ]
        remoteruns = [ remoteconnection.asyncrun() for remoteconnection in self.remotes ]
        externalruns = [ exd.asyncrun() for exd in self.exdrivers ]
        try:
            await asyncio.gather(*driverruns,
                                 *remoteruns,
                                 *externalruns,
                                 self._runserver(),
                                 self._copyfromserver(),
                                 self._sendtoclient()
                                 )
        finally:
            self.stopped.set()
            self._stop = True


    async def _copyfromserver(self):
        """Gets data from serverreaderque.
           For every driver, copy data, if applicable, to driver.readerque
           And for every remote connection if applicable, to its send method"""
        while not self._stop:
            quexit, xmldata = await queueget(self.serverreaderque)
            if quexit:
                continue
            devicename = xmldata.get("device")
            propertyname = xmldata.get("name")

            if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
                if ((xmldata.tag == "setBLOBVector") or (xmldata.tag == "newBLOBVector")) and len(xmldata):
                    data = copy.deepcopy(xmldata)
                    for element in data:
                        element.text = "NOT LOGGED"
                    binarydata = ET.tostring(data)
                    logger.debug(f"RX:: {binarydata.decode('utf-8')}")
                else:
                    binarydata = ET.tostring(xmldata)
                    logger.debug(f"RX:: {binarydata.decode('utf-8')}")

            remconfound = False
            exdriverfound = False

            # check for a getProperties
            if xmldata.tag == "getProperties":
                # if getproperties is targetted at a known device, send it to that device
                if devicename:
                    if devicename in self.devices:
                        # this getProperties request is meant for an attached device
                        await self._queueput(self.devices[devicename].driver.readerque, xmldata)
                        # no need to transmit this anywhere else, continue the while loop
                        self.serverreaderque.task_done()
                        continue
                    for remcon in self.remotes:
                        if devicename in remcon:
                            # this getProperties request is meant for a remote connection
                            await remcon.send(xmldata)
                            remconfound = True
                            break
                    if not remconfound:
                        for exd in self.exdrivers:
                            if devicename in exd:
                                # this getProperties request is meant for an external driver
                                await self._queueput(exd.readerque, xmldata)
                                exdriverfound = True
                                break

            if remconfound:
                # no need to transmit this anywhere else, continue the while loop
                self.serverreaderque.task_done()
                continue

            if exdriverfound:
                # no need to transmit this anywhere else, continue the while loop
                self.serverreaderque.task_done()
                continue


            # transmit xmldata out to remote connections
            if xmldata.tag != "enableBLOB":
                # enableBLOB instructions are not forwarded to remcon's
                for remcon in self.remotes:
                    if not remcon.connected:
                        continue
                    if devicename and (devicename in remcon):
                        # this devicename has been found on this remote,
                        # so it must be a 'new' intended for this connection and
                        # it is not snoopable, since it is data to a device, not from it.
                        await remcon.send(xmldata)
                        remconfound = True
                        break
                    elif xmldata.tag == "getProperties":
                        # either no devicename, or an unknown device
                        # if it were a known devicename the previous block would have handled it.
                        # so send it on all connections
                        await remcon.send(xmldata)
                    elif not xmldata.tag.startswith("new"):
                        # either devicename is unknown, or this data is to/from another driver.
                        # So check if this remcon is snooping on this device/vector
                        # only forward def's and set's, not 'new' vectors which
                        # do not come from a device, but only from a client to the target device.
                        if remcon.clientdata["snoopall"]:
                            await remcon.send(xmldata)
                        elif devicename and (devicename in remcon.clientdata["snoopdevices"]):
                            await remcon.send(xmldata)
                        elif devicename and propertyname and ((devicename, propertyname) in remcon.clientdata["snoopvectors"]):
                            await remcon.send(xmldata)

            if remconfound:
                # no need to transmit this anywhere else, continue the while loop
                self.serverreaderque.task_done()
                continue

            # transmit xmldata out to exdrivers
            if xmldata.tag != "enableBLOB":
                # enableBLOB instructions are not forwarded to external drivers
                for driver in self.exdrivers:
                    if devicename and (devicename in driver):
                        # data is intended for this driver
                        # it is not snoopable, since it is data to a device, not from it.
                        await self._queueput(driver.readerque, xmldata)
                        exdriverfound = True
                        break
                    elif xmldata.tag == "getProperties":
                        # either no devicename, or an unknown device
                        await self._queueput(driver.readerque, xmldata)
                    elif not xmldata.tag.startswith("new"):
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

            if exdriverfound:
                # no need to transmit this anywhere else, continue the while loop
                self.serverreaderque.task_done()
                continue

            # transmit xmldata out to drivers
            for driver in self.drivers:
                if devicename and (devicename in driver):
                    # data is intended for this driver
                    # it is not snoopable, since it is data to a device, not from it.
                    await self._queueput(driver.readerque, xmldata)
                    break
                elif xmldata.tag == "getProperties":
                    # either no devicename, or an unknown device
                    await self._queueput(driver.readerque, xmldata)
                elif not xmldata.tag.startswith("new"):
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

            self.serverreaderque.task_done()
            # now every driver/remcon which needs it has this xmldata

    async def _sendtoclient(self):
        "For every clientconnection, get txque and copy data into it from serverwriterque"
        while not self._stop:
            quexit, xmldata = await queueget(self.serverwriterque)
            if quexit:
                continue
            #  This xmldata of None is an indication to shut the server down
            #  It is set to None when a duplicate devicename is discovered
            if xmldata is None:
                logger.error("A duplicate devicename has caused a server shutdown")
                self.serverwriterque.task_done()
                self.shutdown("A duplicate devicename has caused a server shutdown")
                return
            if logger.isEnabledFor(logging.DEBUG) and self.debug_enable:
                if (xmldata.tag == "setBLOBVector") and len(xmldata):
                    data = copy.deepcopy(xmldata)
                    for element in data:
                        element.text = "NOT LOGGED"
                    binarydata = ET.tostring(data)
                    logger.debug(f"TX:: {binarydata.decode('utf-8')}")
                else:
                    binarydata = ET.tostring(xmldata)
                    logger.debug(f"TX:: {binarydata.decode('utf-8')}")
            for clientconnection in self.connectionpool:
                if clientconnection.connected:
                    await self._queueput(clientconnection.txque, xmldata)
            # task completed
            self.serverwriterque.task_done()

    async def send_message(self, message, timestamp=None):
        """Send system wide message, timestamp should normlly not be set, if
           given, it should be a datetime.datetime object with tz set to timezone.utc"""
        if self._stop:
            return
        if not timestamp:
            timestamp = datetime.now(tz=timezone.utc).replace(tzinfo = None)
        else:
            if not isinstance(timestamp, datetime):
                # invalid timestamp given
                return
            if not (timestamp.tzinfo is None):
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
            quexit, xmldata = await queueget(writerque)
            if quexit:
                continue
            # Check if other drivers/remotes wants to snoop this traffic
            devicename = xmldata.get("device")
            propertyname = xmldata.get("name")

            if xmldata.tag.startswith("new"):
                # drivers should never transmit a new
                # but just in case
                writerque.task_done()
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
                        writerque.task_done()
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
                        writerque.task_done()
                        continue
                    for remcon in self.remotes:
                        if not remcon.connected:
                            continue
                        if devicename in remcon:
                            # this getProperties request is meant for a remote connection
                            await remcon.send(xmldata)
                            foundflag = True
                            break
                    if foundflag:
                        # no need to transmit this anywhere else, continue the while loop
                        writerque.task_done()
                        continue

            # transmit xmldata out to remote connections
            for remcon in self.remotes:
                if xmldata.tag == "getProperties":
                    # either no devicename, or an unknown device
                    # if it were a known devicename the previous block would have handled it.
                    # so send it on all connections
                    await remcon.send(xmldata)
                else:
                    # Check if this remcon is snooping on this device/vector
                    if remcon.clientdata["snoopall"]:
                        await remcon.send(xmldata)
                    elif devicename and (devicename in remcon.clientdata["snoopdevices"]):
                        await remcon.send(xmldata)
                    elif devicename and propertyname and ((devicename, propertyname) in remcon.clientdata["snoopvectors"]):
                        await remcon.send(xmldata)

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


            # traffic from this driver writerque has been sent to other drivers/remotes if they want to snoop.
            # The traffic must also now be sent to the clients.
            # If no clients are connected, do not put this data into
            # the serverwriterque
            for clientconnection in self.connectionpool:
                if clientconnection.connected:
                    # at least one is connected, so this data is put into
                    # serverwriterque, and is then sent to each client by
                    # the _sendtoclient method.
                    await self._queueput(self.serverwriterque, xmldata)
                    break
            # task completed
            writerque.task_done()


class _ClientConnection:

    "Handles a client connection"

    def __init__(self, devices, exdrivers, remotes, serverreaderque):
        # self.txque will have data to be transmitted
        # inserted into it from the IPyServer._sendtoclient()
        # method
        self.txque = asyncio.Queue(6)

        # devices is a dictionary of device name to device
        self.devices = devices
        self.remotes = remotes
        self.exdrivers = exdrivers
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
        if not self.rx is None:
            self.rx.shutdown()
        if not self.tx is None:
            self.tx.shutdown()



    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        self.connected = True
        sendchecker = SendChecker(self.devices, self.exdrivers, self.remotes)
        addr = writer.get_extra_info('peername')
        self.rx = Port_RX(sendchecker, reader)
        self.tx = Port_TX(sendchecker, writer)
        logger.info(f"Connection received from {addr}")
        try:
            txtask = asyncio.create_task(self.tx.run_tx(self.txque))
            rxtask = asyncio.create_task(self.rx.run_rx(self.serverreaderque))
            await asyncio.gather(txtask, rxtask)
        except ConnectionError:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()
        finally:
            self.connected = False
            cleanque(self.txque)
            logger.info(f"Connection from {addr} closed")
