
Development notes
=================

These notes are not user instructions, but are development notes for the indipydriver package internal functionality.

The package has data flows passing between communications ports and devices by various asyncio.Queue() objects.

The IPyDriver class defines queues:

IPyDriver.writerque

IPyDriver.readerque

IPyDriver.snoopque

These all being instances asyncio.Queue(4).

The asyncrun method of the driver contains the following::

        await asyncio.gather(self.comms(self.readerque, self.writerque),   # run communications
                             self.hardware(),        # task to operate device hardware, and transmit updates
                             self._read_readerque(), # task to handle received xml data
                             self._snoophandler(),   # task to handle incoming snoop data
                             *device_handlers,       # each device handles its incoming data
                             *property_handlers      # each property handles its incoming data
                            )


IPyDriver.comms
^^^^^^^^^^^^^^^

When the IPyDriver.asyncrun() is awaited, one task it creates is IPyDriver.comms(self.readerque, self.writerque), so setting the comms attribute to a coroutine which handles these queues is a way of creating different forms of connections.

If IPyDriver.comms is None (the default), and IPyDriver.asyncrun() is called, attribute IPyDriver.comms is set to STDINOUT, imported from module indipydriver.comms, and the driver will communicate by stdin and stdout.

If method IPyDriver.listen() is called first, attribute IPyDriver.comms is set to Portcomms, imported from module indipydriver.comms, and the driver will listen on a port when IPyDriver.asyncrun() is awaited.

If IPyDriver.comms is None, and an IPyServer is created with this driver, it will set attribute comms to an instance of _DriverComms(), defined in module indipydriver.ipyserver, and the IPyServer.asyncrun method will call each drivers asyncrun method.


IPyDriver.hardware
^^^^^^^^^^^^^^^^^^

Initially a coroutine only containing pass. Overwrite this if required to control your hardware.


IPyDriver snooper attributes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The IPyDriver class defines attributes::

    self.snoopall = False           # gets set to True if it is snooping everything
    self.snoopdevices = set()       # gets set to a set of device names
    self.snoopvectors = set()       # gets set to a set of (devicename,vectorname) tuples

snoopall gets set to True if the driver sends a getProperties without defining a devicename. In other words it wants to snoop on everything.

snoopdevices gets devicenames added to it if the driver sends a getProperties with a devicename but no vectorname. In other words it wants to snoop on everything sent by that device.

snoopvectors get (devicename, vectorname) tuples added if the driver sends a getProperties with a devicename and a vectorname. In other words it wants to snoop on a particular vector.

Note: devices are not added to these sets if they are devices already owned by the driver. There is no point in a driver snooping on its own devices.


IPyServer
^^^^^^^^^

The IPyServer class takes a list of driver instances and creates a listening port, with a pool of _ClientConnection objects which accept incoming client connections, and can also create outgoing connections to remote INDI servers. Each _ClientConnection has a txque queue.

The IPyServer class has two queues defined with asyncio.Queue(6).

IPyServer.serverwriterque - where data will be sent to client connections.

IPyServer.serverreaderque - where data will be received from clients.

IPyServer has method add_remote(self, host, port, blob_enable="Never", debug_enable=False) which make outgoing calls to remote INDI servers. The method uses the indipyclient package to create a child class of an indipyclient.IPyClient object. This child class, defined as indipydriver.remote.RemoteConnection(IPyClient) overwrites the rxevent(self, event) method of IPyClient to accept data from the remote service and passes it to other remote connections, to driver readerques and to IPyServer.serverwriterque.

The IPyServer.asyncrun() coroutine creates a task which reads data from IPyServer.serverwriterque and copies it to each connected _ClientConnection.txque.

Each connection calls comms.Port_TX, where the txque is read, it is checked against a (per connection) SendChecker object which is populated with permissions dependent on enableBLOB's received, and if allowed, it is transmitted to the server port.


IPyDriver.writerque
^^^^^^^^^^^^^^^^^^^

The driver, devices and propertyvectors - when called to send data, create the xmldata object, and call the IPyDriver.send(xmldata) method.

This method puts data into IPyDriver.writerque, which is passed into the driver.comms coroutine.

If stdin/out is used, the writerque is read in module comms.STDOUT_TX and data passed to stdout.

If the listen method is used, the writerque is read in module comms.Port_TX, it is checked against a indipydriver.comms.SendChecker object which is populated with permissions dependent on enableBLOB's received, and if allowed, it is transmitted to the server port.

If IPyServer is used, possibly with multiple drivers, an IPyServer.serverwriterque is created.

Multiple ipyserver._DriverComms objects are created, one for each driver, and assigned to the driver.comms attribute.

Each _DriverComms.__call__ method does several things:

It reads the driver.writerque and puts the data into the IPyServer.serverwriterque.  This combines all the driver writer queues into one queue. The data from the driver.writerque is also tested against other drivers snooping requirements, (by testing the other drivers snoopall, snoopdevices, snoopvectors attributes) and if another driver wants to snoop it, a copy is placed into the other drivers readerque.

Similarly it also checks remote server connections snooping requirements, and if a remote connection wants to snoop it, a copy is sent by calling the remote connection send method.


IPyDriver.readerque
^^^^^^^^^^^^^^^^^^^

When a client connection receives data, the comms.Port_RX reads the input, updates permission status on the (per connection) BLOBSstatus object and ..

If listen() is used, the comms.Port_RX places the data into the IPyDriver.readerque.

If IPyServer is used, comms.Port_RX places the parsed xmldata into an IPyServer.serverreaderque.

The IPyServer.asyncrun() coroutine reads data from IPyServer.serverreaderque, it checks the xmldata, and if ok, passes it to the right driver readerque.

If received devicename is not given (getProperties) it is passed to every driver readerque.

If received devicename matches a device in a driver served by IPyServer, the received data is passed to that driver.

If the devicename does not belong to this server, check if any driver is snooping on this device (by testing the other drivers snoopall, snoopdevices, snoopvectors attributes), and if so, places a copy in that drivers readerque.

The drivers _read_readerque() co-routine reads the IPyDriver.readerque and checks it, and either puts the data into a device 'dataque', or into the drivers snoopque, where it is immediately handled by the drivers _snoophandler() coroutine where snoopevents are created, and the driver snoopevent(event) coroutine is called where the event is handled by user code.

If set into a device.dataque, the device coroutine _handler() gets the data, checks it, and puts it into the correct propertyvector.dataque

The propertyvector _handler() co-routine, receives the data, creates an event containing properties extracted from the data, and calls the driver rxevent(event) co-routine, where the event is handled by the users code.
