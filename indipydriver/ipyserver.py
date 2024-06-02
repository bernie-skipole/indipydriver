

import collections, asyncio, sys

import xml.etree.ElementTree as ET

from functools import partialmethod

import logging
logger = logging.getLogger(__name__)

from .ipydriver import IPyDriver

from .comms import Port_RX, Port_TX, cleanque, SendChecker, TXTimer

from .remote import RemoteConnection


class IPyServer:

    """Once an instance of his class is created, the asyncrun method
       should be awaited which will open a port, and the INDI service
       will be available for clients to connect.

       drivers is a list of IPyDriver objects this driver handles,
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

       """


    def __init__(self, drivers, *, host="localhost", port=7624, maxconnections=5):

        # traffic is transmitted out on the serverwriterque
        self.serverwriterque = asyncio.Queue(6)
        # and read in from the serverreaderque
        self.serverreaderque = asyncio.Queue(6)

        if maxconnections<1 or maxconnections>10:
            raise ValueError("maxconnections should be a number between 1 and 10 inclusive.")
        self.maxconnections = maxconnections

        # this is a dictionary of device name to device
        self.devices = {}

        # self.remotes is a list of RemoteConnection objects running connections to remote servers
        # this list is populated by calling self.add_remote(host, port, debug_enable)
        self.remotes = []

        for driver in drivers:
            if not isinstance(driver, IPyDriver):
                raise TypeError("The drivers set in IPyServer must all be IPyDrivers")
            if not driver.comms is None:
                 raise RuntimeError("A driver communications method has already been set, there can only be one")
            devicesindriver = driver.devices.copy()
            for devicename in devicesindriver:
                if devicename in self.devices:
                    # duplicate devicename
                    raise ValueError(f"Device name {devicename} is duplicated in the attached drivers.")
            self.devices.update(devicesindriver)

        self.connectionpool = []
        for clientconnection in range(0, maxconnections):
            self.connectionpool.append(_ClientConnection(self.devices, self.remotes, self.serverreaderque))

        for driver in drivers:
            # an instance of _DriverComms is created for each driver
            # each _DriverComms object has a list of drivers, not including its own driver
            # these will be used to send snooping traffic, sent by its own driver
            otherdrivers = [ d for d in drivers if not d is driver]
            driver.comms = _DriverComms(self.serverwriterque, self.connectionpool, otherdrivers, self.remotes)

        self.drivers = drivers
        self.host = host
        self.port = port


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
                                  devices = self.devices,
                                  drivers = self.drivers,
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


    async def _runserver(self):
        "Runs the server on the given host and port"
        logger.info(f"{self.__class__.__name__} listening on {self.host} : {self.port}")
        server = await asyncio.start_server(self.handle_data, self.host, self.port)
        await server.serve_forever()


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
        """Runs the server together with its drivers and any remote connections."""
        driverruns = [ driver.asyncrun() for driver in self.drivers ]
        remoteruns = [ remoteconnection.asyncrun() for remoteconnection in self.remotes ]
        await asyncio.gather(*driverruns,
                             *remoteruns,
                             self._runserver(),
                             self._copyfromserver(),
                             self._sendtoclient()
                             )


    async def _copyfromserver(self):
        """Gets data from serverreaderque.
           For every driver, copy data, if applicable, to driver.readerque
           And for every remote connection if applicable, to its send method"""
        while True:
            await asyncio.sleep(0)
            xmldata = await self.serverreaderque.get()
            devicename = xmldata.get("device")
            propertyname = xmldata.get("name")

            remconfound = False

            # check for a getProperties
            if xmldata.tag == "getProperties":
                # if getproperties is targetted at a known device, send it to that device
                if devicename:
                    if devicename in self.devices:
                        # this getProperties request is meant for an attached device
                        await self.devices[devicename].driver.readerque.put(xmldata)
                        # no need to transmit this anywhere else, continue the while loop
                        self.serverreaderque.task_done()
                        continue
                    for remcon in self.remotes:
                        if devicename in remcon:
                            # this getProperties request is meant for a remote connection
                            remcon.send(xmldata)
                            remconfound = True
                            break

            if remconfound:
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
                        remcon.send(xmldata)
                        remconfound = True
                        break
                    elif xmldata.tag == "getProperties":
                        # either no devicename, or an unknown device
                        # if it were a known devicename the previous block would have handled it.
                        # so send it on all connections
                        remcon.send(xmldata)
                    elif not xmldata.tag.startswith("new"):
                        # either devicename is unknown, or this data is to/from another driver.
                        # So check if this remcon is snooping on this device/vector
                        # only forward def's and set's, not 'new' vectors which
                        # do not come from a device, but only from a client to the target device.
                        if remcon.clientdata["snoopall"]:
                            remcon.send(xmldata)
                        elif devicename and (devicename in remcon.clientdata["snoopdevices"]):
                            remcon.send(xmldata)
                        elif devicename and propertyname and ((devicename, propertyname) in remcon.clientdata["snoopvectors"]):
                            remcon.send(xmldata)

            if remconfound:
                # no need to transmit this anywhere else, continue the while loop
                self.serverreaderque.task_done()
                continue

            # transmit xmldata out to drivers
            for driver in self.drivers:
                if devicename and (devicename in driver):
                    # data is intended for this driver
                    # it is not snoopable, since it is data to a device, not from it.
                    await driver.readerque.put(xmldata)
                    break
                elif xmldata.tag == "getProperties":
                    # either no devicename, or an unknown device
                    await driver.readerque.put(xmldata)
                elif not xmldata.tag.startswith("new"):
                    # either devicename is unknown, or this data is to/from another driver.
                    # So check if this driver is snooping on this device/vector
                    # only forward def's and set's, not 'new' vectors which
                    # do not come from a device, but only from a client to the target device.
                    if driver.snoopall:
                        await driver.readerque.put(xmldata)
                    elif devicename and (devicename in driver.snoopdevices):
                        await driver.readerque.put(xmldata)
                    elif devicename and propertyname and ((devicename, propertyname) in driver.snoopvectors):
                        await driver.readerque.put(xmldata)

            self.serverreaderque.task_done()
            # now every driver/remcon which needs it has this xmldata



    async def _sendtoclient(self):
        "For every clientconnection, get txque and copy data into it from serverwriterque"
        while True:
            await asyncio.sleep(0)
            xmldata = await self.serverwriterque.get()
            for clientconnection in self.connectionpool:
                if clientconnection.connected:
                    await clientconnection.txque.put(xmldata)
            # task completed
            self.serverwriterque.task_done()



class _DriverComms:

    """An instance of this is created for each driver, which calls the __call__
       method.  Any data the driver wishes to be send will be taken
       from the drivers writerque and transmitted to the client by placing it
       into the serverwriterque"""

    def __init__(self, serverwriterque, connectionpool, otherdrivers, remotes):

        self.serverwriterque = serverwriterque
        # connectionpool is a list of ClientConnection objects, which is used
        # to test if a client is connected
        self.connectionpool = connectionpool
        # self.connected is read by the driver, and in this case is always True
        # as the driver is connected to IPyServer, which handles snooping traffic,
        # even if no client is connected
        self.connected = True
        # self.otherdrivers is set to a list of drivers, not including the driver
        # this object is attached to.
        self.otherdrivers = otherdrivers
        # self.remotes is a list of connections to remote servers
        self.remotes = remotes


    async def __call__(self, readerque, writerque):
        """Called by the driver, should run continuously.
           reads writerque from the driver, and sends xml data to the network"""
        while True:
            await asyncio.sleep(0)
            xmldata = await writerque.get()
            # Check if other drivers/remotes wants to snoop this traffic
            devicename = xmldata.get("device")
            propertyname = xmldata.get("name")

            if xmldata.tag.startswith("new"):
                # drivers should never transmit a new
                # but just in case
                writerque.task_done()
                logger.error(f"Driver transmitted invalid tag {xmldata.tag}")
                continue

            # check for a getProperties
            if xmldata.tag == "getProperties":
                foundflag = False
                # if getproperties is targetted at a known device, send it to that device
                if devicename:
                    for driver in self.otherdrivers:
                        if devicename in driver:
                            # this getProperties request is meant for an attached driver/device
                            await driver.readerque.put(xmldata)
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
                            remcon.send(xmldata)
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
                    remcon.send(xmldata)
                else:
                    # Check if this remcon is snooping on this device/vector
                    if remcon.clientdata["snoopall"]:
                        remcon.send(xmldata)
                    elif devicename and (devicename in remcon.clientdata["snoopdevices"]):
                        remcon.send(xmldata)
                    elif devicename and propertyname and ((devicename, propertyname) in remcon.clientdata["snoopvectors"]):
                        remcon.send(xmldata)

            # transmit xmldata out to other drivers
            for driver in self.otherdrivers:
                if xmldata.tag == "getProperties":
                    # either no devicename, or an unknown device
                    await driver.readerque.put(xmldata)
                else:
                    # Check if this driver is snooping on this device/vector
                    if driver.snoopall:
                        await driver.readerque.put(xmldata)
                    elif devicename and (devicename in driver.snoopdevices):
                        await driver.readerque.put(xmldata)
                    elif devicename and propertyname and ((devicename, propertyname) in driver.snoopvectors):
                        await driver.readerque.put(xmldata)


            # traffic from this driver writerque has been sent to other drivers/remotes if they want to snoop
            # the traffic must also now be sent to the clients.
            # If no clients are connected, do not put this data into
            # the serverwriterque
            for clientconnection in self.connectionpool:
                if clientconnection.connected:
                    # at least one is connected, so this data is put into
                    # serverwriterque, and is then sent to each client by
                    # the _sendtoclient method.
                    await self.serverwriterque.put(xmldata)
                    break
            # task completed
            writerque.task_done()


class _ClientConnection:

    "Handles a client connection"

    def __init__(self, devices, remotes, serverreaderque):
        # self.txque will have data to be transmitted
        # inserted into it from the IPyServer._sendtoclient()
        # method
        self.txque = asyncio.Queue(6)

        # devices is a dictionary of device name to device
        self.devices = devices
        self.remotes = remotes
        self.serverreaderque = serverreaderque
        # self.connected is True if this pool object is running a connection
        self.connected = False

        # timer used to force a data transmission after timeout seconds
        # this will cause an exception if the connection is broken and will shut down
        # the connection
        self.txtimer = TXTimer(timeout = 15)
        self.rxtimer = TXTimer(timeout = 15)


    async def _monitor_connection(self):
        """If connected, send def vectors every timeout seconds
           This ensures that if the connection has failed, due to the client disconnecting, the write
           to the port operation will cause a failure exception which will close the connection"""
        while True:
            await asyncio.sleep(5)
            # this is tested every five seconds
            # If a remcon is connected, leave the send def vectors to the remcon
            # by increasing the timeout, so the remcon timer times out first
            if self.remotes:
                for remcon in self.remotes:
                    if remcon.connected:
                        self.txtimer.timeout = 25
                        self.rxtimer.timeout = 25
                        break
                else:
                    self.txtimer.timeout = 15
                    self.rxtimer.timeout = 15
            if self.connected and self.txtimer.elapsed() and self.rxtimer.elapsed():
                # no transmission in timeout seconds so send defVectors
                for device in self.devices.values():
                    if not device.enable:
                        continue
                    for vector in device.values():
                        if not vector.enable:
                            continue
                        xmldata =  vector._make_defVector()
                        if xmldata:
                            await self.txque.put(xmldata)


    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        self.connected = True
        sendchecker = SendChecker(self.devices, self.remotes)
        addr = writer.get_extra_info('peername')
        rx = Port_RX(sendchecker, reader, self.rxtimer)
        tx = Port_TX(sendchecker, writer, self.txtimer)
        logger.info(f"Connection received from {addr}")
        try:
            txtask = asyncio.create_task(tx.run_tx(self.txque))
            rxtask = asyncio.create_task(rx.run_rx(self.serverreaderque))
            montask = asyncio.create_task(self._monitor_connection())
            await asyncio.gather(txtask, rxtask, montask)
        except ConnectionError:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()
            montask.cancel()
            cleanque(self.txque)
        logger.info(f"Connection from {addr} closed")
