
Development notes
=================

These notes are not user instructions, but are development notes for the indipydriver package internal functionality.

The package has data flows passing between communications ports and devices by various asyncio.Queue() objects.

The driver IPyDriver class, defines queues:

IPyDriver.writerque

IPyDriver.readerque

IPyDriver.snoopque

These all being instances asyncio.Queue(4).

The asyncrun method of the driver contains the following::

        await asyncio.gather(*self._tasks,           # any tasks included when creating the driver
                             self.comms(self.readerque, self.writerque),   # run communications
                             self.hardware(),        # task to operate device hardware, and transmit updates
                             self._read_readerque(), # task to handle received xml data
                             self._snoophandler(),   # task to handle incoming snoop data
                             *device_handlers,       # each device handles its incoming data
                             *property_handlers      # each property handles its incoming data
                            )


IPyDriver.comms
^^^^^^^^^^^^^^^

If method IPyDriver.listen() is called, attribute comms is set to Portcomms, imported from module .comms, and the driver will listen on a port.

If comms is None, and IPyDriver.asyncrun() is called, attribute comms is set to STDINOUT, imported from module .comms, and the driver will communicate by stdin and stdout.

If comms is None, and an IPyServer is created with this driver, it will set attribute comms to an instance of _DriverComms(), defined in module ipyserver.


IPyDriver.hardware
^^^^^^^^^^^^^^^^^^

Initially a coroutine only containing pass. overwrite


IPyDriver.writerque
^^^^^^^^^^^^^^^^^^^

The driver, devices and propertyvectors - when called to send data, create the xmldata object, and call the IPyDriver.send(xmldata) method.

This method puts data into IPyDriver.writerque, which as can be seen from the above, is passed into the driver.comms coroutine.

If stdin/out is used, the writerque is read in module comms.STDOUT_TX and data passed to stdout.

If the listen method is used, the writerque is read in module comms.Port_TX, it is checked against a BLOBSstatus object which is populated with permissions dependent on enableBLOB's received, and if allowed, it is transmitted to the server port.

If IPyServer is used, possibly with multiple drivers, an IPyServer.serverwriterque is created.

Multiple ipyserver._DriverComms objects are created, one for each driver, and assigned to the driver.comms attribute, each reads the driver.writerque and puts the data into the IPyServer.serverwriterque.  This combines all the driver writer queues into one queue. The data from the driver.writerque is also tested against other drivers snooping requirements, and if another driver wants to snoop it, a copy is placed into the other drivers _DriverComms.rxque.

A pool of ipyserver._ClientConnection objects is created, and one is assigned per client connection. Each has a _ClientConnection.txque queue.

The IPyServer.asyncrun() coroutine creates a task which reads data from IPyServer.serverwriterque and copies it to each connected _ClientConnection.txque.

Each connection calls comms.Port_TX, where the txque is read, it is checked against a (per connection) BLOBSstatus object which is populated with permissions dependent on enableBLOB's received, and if allowed, it is transmitted to the server port.


IPyDriver.readerque
^^^^^^^^^^^^^^^^^^^

When a client connection receives data, the comms.Port_RX reads the input, updates permission status on the (per connection) BLOBSstatus object and ..

If listen() is used, the comms.Port_RX places the data into the IPyDriver.readerque.

If IPyServer is used, comms.Port_RX places the parsed xmldata into an IPyServer.serverreaderque.

An ipyserver._DriverComms object is created for each driver. Each has a _DriverComms.rxque.

The IPyServer.asyncrun() coroutine creates a task copyreceivedtodriversrxque which reads data from IPyServer.serverreaderque and copies it to each drivers _DriverComms.rxque, this copy function checks the xmldata to get it to the right driver.

Each driver is calling its _DriverComms object, which places its rxque contents into the drivers IPyDriver.readerque

So in both cases, the single driver, or each individual driver now has received data in its IPyDriver.readerque.

The drivers _read_readerque() co-routine reads the IPyDriver.readerque and checks it, and either puts the data either into a device 'dataque', or into the drivers snoopque, where it is immediately handled by the drivers _snoophandler() coroutine where snoopevents are created, and the driver snoopevent(event) coroutine is called where the event is handled by user code.

If set into a device.dataque, the device coroutine _handler() gets the data, checks it, and puts it into the correct propertyvector.dataque

The propertyvector _handler() co-routine, receives the data, creates an event containing properties extracted from the data, and calls the driver clientevent(event) co-routine, where the event is handled by the users code.
