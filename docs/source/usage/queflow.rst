
Development notes
=================

These notes are not user instructions, but are development notes for the indipydriver package internal functionality.

The package has data flows passing between communications ports and devices by various asyncio.Queue() objects.

The driver IPyDriver class, defines queues:

IPyDriver.writerque

IPyDriver.readerque

IPyDriver.snoopque

The asyncrun method of the driver contains the following::

        await asyncio.gather(self.comms(self.readerque, self.writerque),   # run communications
                             self.hardware(),        # task to operate device hardware, and transmit updates
                             self._read_readerque(), # task to handle received xml data
                             self._snoophandler(),   # task to handle incoming snoop data
                             *device_handlers,       # each device handles its incoming data
                             *property_handlers      # each property handles its incoming data
                            )



IPyDriver.writerque
^^^^^^^^^^^^^^^^^^^

The driver, devices and propertyvectors - when called to send data, create the xmldata object, and call the IPyDriver.send(xmldata) method.

This method puts data into IPyDriver.writerque, which as can be seen from the above, is passed into the driver.comms coroutine.

If stdin/out is used, the writerque is read in module comms.STDOUT_TX and data passed to stdout.

If the listen method is used, the writerque is read in module comms.Port_TX, it is checked against a BLOBSstatus object which is populated with permissions dependent on enableBLOB's received, and if allowed, it is transmitted to the server port.

If IPyServer is used, possibly with multiple drivers, an IPyServer.serverwriterque is created.

Multiple ipyserver._DriverComms objects are created, one for each driver, and assigned to the driver.comms attribute, each reads the driver.writerque and puts the data into the IPyServer.serverwriterque.  This combines all the driver writer queues into one queue.

A pool of ipyserver._ClientConnection objects is created, and one is assigned per client connection. Each has a _ClientConnection.txque queue.

The IPyServer.asyncrun() coroutine creates a task which reads data from IPyServer.serverwriterque and copies it to each connected _ClientConnection.txque queue.

Each connection calls comms.Port_TX, where the txque is read, it is checked against a (per connection) BLOBSstatus object which is populated with permissions dependent on enableBLOB's received, and if allowed, it is transmitted to the server port.


IPyDriver.readerque
^^^^^^^^^^^^^^^^^^^
