

import collections, asyncio, sys

import xml.etree.ElementTree as ET

from functools import partialmethod

from .ipydriver import IPyDriver

from .comms import Port_RX, Port_TX, cleanque, BLOBSstatus, TXTimer


class IPyServer:

    """An instance should be created with:

       drivers is a list of IPyDriver objects this driver handles.

       host and port are "localhost" and 7624 as default

       maxconnections is the number of simultaneous client connections
       accepted, with a default of 5. The number given should be
       between 1 and 10 inclusive.

       The awaitable asyncrun method should be run in an async loop.
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
            self.connectionpool.append(_ClientConnection(self.devices, self.serverreaderque))

        for driver in drivers:
            # an instance of _DriverComms is created for each driver
            # each _DriverComms object has a list of drivers, not including its own driver
            # these will be used to send snooping traffic, sent by its own driver
            otherdrivers = [ d for d in drivers if not d is driver]
            driver.comms = _DriverComms(self.serverwriterque, self.connectionpool, otherdrivers)

        for driver in drivers:
            driver.comms.otherdrivers = [ d for d in drivers if not d is driver]

        self.drivers = drivers
        self.host = host
        self.port = port

    async def runserver(self):
        "Runs the server on the given host and port"
        server = await asyncio.start_server(self.handle_data, self.host, self.port)
        try:
            await server.serve_forever()
        except KeyboardInterrupt as e:
            server.close()
            raise e

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
        """Runs the server together with its drivers."""
        driverruns = [ driver.asyncrun() for driver in self.drivers ]
        await asyncio.gather(*driverruns,
                             self.runserver(),
                             self.copyreceivedtodriversrxque(),
                             self.copytransmittedtoclienttxque()
                             )


    async def copyreceivedtodriversrxque(self):
        "For every driver, get rxque and copy data into it from serverreaderque"
        while True:
            await asyncio.sleep(0)
            xmldata = await self.serverreaderque.get()
            devicename = xmldata.get("device")
            propertyname = xmldata.get("name")
            if devicename is None:
                # if no devicename - goes to every driver (getproperties)
                for driver in self.drivers:
                    await driver.comms.rxque.put(xmldata)
            elif devicename in self.devices:
                # self.devices is a dictionary of device name to device
                driver = self.devices[devicename].driver
                # data is intended for this driver
                await driver.comms.rxque.put(xmldata)
            else:
                # devicename is unknown, check if driver is snooping on this device, vector
                for driver in self.drivers:
                    if driver.snoopall:
                        await driver.comms.rxque.put(xmldata)
                    elif devicename in driver.snoopdevices:
                        await driver.comms.rxque.put(xmldata)
                    elif not propertyname is None:
                        if (devicename, propertyname) in driver.snoopvectors:
                            await driver.comms.rxque.put(xmldata)
                    # else not snooping, so don't bother sending it to the driver
            self.serverreaderque.task_done()
            # now every driver.comms object which needs it has this xmldata in its rxque


    async def copytransmittedtoclienttxque(self):
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
       method, expecting xmldata to be received from the client and placed
       in readerque, and any data the driver wishes to be sent should
       be taken from the writerque and transmitted to the client by placing it
       into the serverwriterque"""

    def __init__(self, serverwriterque, connectionpool, otherdrivers):

        # self.rxque will have data received from the network
        # inserted into it from the IPyServer.copyreceivedtodriversrxque()
        # method
        self.rxque = asyncio.Queue(6)
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


    async def __call__(self, readerque, writerque):
        "Called by the driver, should run continuously to add and read the queues"
        await asyncio.gather(self.handleread(readerque),
                             self.handlewrite(writerque))

    async def handleread(self, readerque):
        "reads rxque, and sends xml data to the driver"
        while True:
            await asyncio.sleep(0)
            xmldata = await self.rxque.get()
            await readerque.put(xmldata)
            # task completed
            self.rxque.task_done()

    async def handlewrite(self, writerque):
        "reads writerque from the driver, and sends xml data to the network"
        while True:
            await asyncio.sleep(0)
            xmldata = await writerque.get()
            # Check if other drivers wants to snoop this traffic
            devicename = xmldata.get("device")
            propertyname = xmldata.get("name")
            if devicename is None:
                # if no devicename - goes to every other driver (getproperties)
                for driver in self.otherdrivers:
                    await driver.comms.rxque.put(xmldata)
            else:
                for driver in self.otherdrivers:
                    if driver.snoopall:
                        await driver.comms.rxque.put(xmldata)
                    elif devicename in driver.snoopdevices:
                        await driver.comms.rxque.put(xmldata)
                    elif not propertyname is None:
                        if (devicename, propertyname) in driver.snoopvectors:
                            await driver.comms.rxque.put(xmldata)
            # traffic from one driver has been sent to other drivers if they want to snoop
            # the traffic must also now be sent to the clients
            # If no clients are connected, do not put this data into
            # the serverwriterque
            for clientconnection in self.connectionpool:
                if clientconnection.connected:
                    # at least one is connected, so this data is put into
                    # serverwriterque, and is then sent to each client by
                    # the copytransmittedtoclienttxque method.
                    await self.serverwriterque.put(xmldata)
                    break
            # task completed
            writerque.task_done()


class _ClientConnection:

    "Handles a client connection"

    def __init__(self, devices, serverreaderque):
        # self.txque will have data to be transmitted
        # inserted into it from the IPyServer.copytransmittedtoclienttxque()
        # method
        self.txque = asyncio.Queue(6)

        # devices is a dictionary of device name to device
        self.devices = devices
        self.serverreaderque = serverreaderque
        # self.connected is True if this pool object is running a connection
        self.connected = False

        # timer used to force a data transmission after timeout seconds
        # this will cause an exception if the connection is broken and will shut down
        # the connection
        self.timer = TXTimer(timeout = 15)


    async def _monitor_connection(self):
        """If connected and self.txque is empty, send def vectors every timeout seconds
           This ensures that if the connection has failed, due to the client disconnecting, the write
           to the port operation will cause a failure exception which will close the connection"""
        while True:
            await asyncio.sleep(5)
            # this is tested every five seconds
            if self.connected and self.txque.empty():
                 # only need to test if the queue is empty
                if self.timer.elapsed():
                    # no transmission in timeout seconds so send defVectors
                    for device in self.devices.values():
                        for vector in device.values():
                            xmldata =  vector._make_defVector()
                            await self.txque.put(xmldata)


    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        self.connected = True
        blobstatus = BLOBSstatus(self.devices)
        rx = Port_RX(blobstatus, reader)
        tx = Port_TX(blobstatus, writer, self.timer)
        try:
            txtask = asyncio.create_task(tx.run_tx(self.txque))
            rxtask = asyncio.create_task(rx.run_rx(self.serverreaderque))
            montask = asyncio.create_task(self._monitor_connection())
            await asyncio.gather(txtask, rxtask, montask)
        except ConnectionResetError:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()
            montask.cancel()
            cleanque(self.txque)
