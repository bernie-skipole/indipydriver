

import collections, asyncio, datetime, sys

import xml.etree.ElementTree as ET

from functools import partialmethod

from .ipydriver import IPyDriver

from .comms import Port_RX, Port_TX


class IPyServer:

    """An instance should be created with:

       drivers is a list of IPyDriver objects this driver handles.

       host and port are "localhost" and 7624 as default

       maxconnections is the number of simultaneous client connections
       accepted, with a default of 5. The number given should be
       between 1 and 10 inclusive.

       The awaitable asyncrun method should be run in an async loop.
       """



    def __init__(self, drivers, host="localhost", port=7624, maxconnection=5):

        # traffic is transmitted out on the serverwriterque
        self.serverwriterque = asyncio.Queue(6)
        # and read in from the serverreaderque
        self.serverreaderque = asyncio.Queue(6)

        if maxconnections<1 or maxconnections>10:
            raise ValueError("maxconnections should be a number between 1 and 10 inclusive.")
        self.maxconnections = maxconnections

        self.connectionpool = []
        for clientconnection in range(0, maxconnections):
            self.connectionpool.append(_ClientConnection(self.serverreaderque, self.serverwriterque))


        for driver in drivers:
            if not isinstance(driver, IPyDriver):
                raise TypeError("The drivers set in IPyServer must all be IPyDrivers")
            # set the comms for each driver
            if not driver.comms is None:
                 raise RuntimeError("A driver communications method has already been set, there can only be one")
            # an instance of _DriverComms is created for each driver
            driver.comms = _DriverComms(self.serverwriterque, self.connectionpool)
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
        """Gathers tasks to be run simultaneously"""
        driverruns = [ driver.asyncrun() for driver in self.drivers ]
        await asyncio.gather(*driverruns,
                             self.runserver(),
                             self.copyreceivedtodriversrxque()
                             )


    async def copyreceivedtodriversrxque(self):
        "For every driver, get rxque and copy data into it from serverreaderque"
        while True:
            await asyncio.sleep(0)
            xmldata = await self.serverreaderque.get()
            for driver in self.drivers
                # should check data is for the driver
                await driver.comms.rxque.put(xmldata)
            self.serverreaderque.task_done()
            # now every driver.comms object has this xmldata in its rxque



class _DriverComms:

    """An instance of this is created for each driver, which calls the __call__
       method, expecting xmldata to be received from the client and placed
       in readerque, and any data the driver wishes to be sent should
       be taken from the writerque and transmitted to the client by placing it
       into the serverwriterque"""

    def __init__(self, serverwriterque, connectionpool):
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
            # should check if this driver wants to snoop

            # If no clients are connected, do not put this data into
            # the serverwriterque
            for clientconnection in self.connectionpool:
                if clientconnection.connected:
                    await self.serverwriterque.put(xmldata)
                    # task completed
                    writerque.task_done()
                    break
            else:
                # no client connected, discard this data
                # if xmldata is a file pointer, close it
                if (xmldata.tag == "setBLOBVector") and len(xmldata):
                    # xmldata is a setBLOBVector containing blobs
                    for oneblob in xmldata.iter('oneBLOB'):
                        # get the filepointer
                        fp = oneblob.text
                        if hasattr(fp 'close'):
                            fp.close()



class _ClientConnection:

    "Handles a client connection"

    def __init__(self, serverreaderque, serverwriterque):
        self.serverreaderque = serverreaderque
        self.serverwriterque = serverwriterque
        # self.connected is True if this pool object is running a connection
        self.connected = False

    async def handle_data(self, reader, writer):
        "Used by asyncio.start_server, called to handle a client connection"
        self.connected = True
        rx = Port_RX(reader)
        tx = Port_TX(writer)
        try:
            txtask = asyncio.create_task(tx.run_tx(self.serverwriterque))
            rxtask = asyncio.create_task(rx.run_rx(self.serverreaderque))
            await txtask
            await rxtask
        except ConnectionResetError:
            self.connected = False
            txtask.cancel()
            rxtask.cancel()







