

import collections, asyncio, datetime, sys

import xml.etree.ElementTree as ET

from functools import partialmethod

from .ipydriver import IPyDriver

from .comms import Port_RX, Port_TX


class IPyServer:

    """An instance should be created with:

       drivers is a list of IPyDriver objects this driver handles.

       host and port are "localhost" and 7624 as default

       The awaitable asyncrun method should be run in an async loop.
       """



    def __init__(self, drivers, host="localhost", port=7624):

        # traffic is transmitted out on the serverwriterque  # may have to create a que for each connection???
        self.serverwriterque = asyncio.Queue(6)
        # and read in from the serverreaderque
        self.serverreaderque = asyncio.Queue(6)

        for driver in drivers:
            if not isinstance(driver, IPyDriver):
                raise TypeError("The drivers set in IPyServer must all be IPyDrivers")
            # set the comms for each driver
            if not driver.comms is None:
                 raise RuntimeError("A driver communications method has already been set, there can only be one")
            # an instance of _DriverComms is created for each driver
            driver.comms = _DriverComms(driver, self.serverwriterque)
        self.drivers = drivers
        self.host = host
        self.port = port
        self.connected = False

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
        if self.connected:
            # already connected, can only handle one connection
            writer.close()
            await writer.wait_closed()
            return
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

    def __init__(self, serverwriterque):
        # self.rxque will have data received from the network
        # inserted into it from the IPyServer.copyreceivedtodriversrxque()
        # method
        self.rxque = asyncio.Queue(6)
        self.serverwriterque = serverwriterque


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
            await self.serverwriterque.put(xmldata)
            # task completed
            self.writerque.task_done()







