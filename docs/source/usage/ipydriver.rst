IPyDriver
=========

Typically you would create a subclass of IPyDriver.

The driver has methods which can be overwritten.

**async def rxevent(self, event)**

This is called whenever data is received from the client, typically to set an instrument parameter. The event object describes the received data, and you provide the code which then controls your instrument, event objects are described at :ref:`rxevents`.

**async def hardware(self)**

This could be a contuously running coroutine which you can use to operate your instruments, and if required send updates to the client.

**async def snoopevent(self, event)**

This is used if the device is monitoring the data sent by other devices, these event objects are described at :ref:`snoopevents`.

IPyDriver is a mapping of devicename:deviceobject, so your code in these methods could access a specific device using self['devicename'].

As well as the methods documented below, dict methods are available such as get() and iteration through keys(), values() and items().

Similarly a Device object is a mapping to a vector, so to access a vector you could use self['devicename']['vectorname'].

----

.. autoclass:: indipydriver.IPyDriver
   :members:

----

The ipydriver object has attributes:

**driverdata** - The dictionary of named arguments you have optionally set in the constructor.

This is particularly useful to pass in any object which controls your instrument, or device names
if you do not want to hard code names into the driver.

**auto_send_def** - As default this is set to True.

With auto_send_def set to True, whenever a getProperties event is received from a client, a
vector send_defVector() method will be called, automatically replying with the vector definition.
If set to False, the driver developer will need to test for a getProperties event, and implement
a send_defVector() in the rxevent method. Possibly one reason you may want to do this is to send
a message with every vector definition.

**stop** - Normally False, but set to True when the driver shutdown() method is called.

**stopped** - An asyncio.Event() object, await driver.stopped.wait() will block until the driver stops.

**debug_enable** - As default this is set to False.

With debug_enable set to False, then xml traffic will not be logged at the driver level, but will still be logged at the server level which logs all traffic between server and attached clients. See the logging section of this documentation for further details.

----

There are three ways a driver can be run, assuming 'driver' is an instance of this class.

This coroutine outputs the xml data on stdout, and reads it on stdin::

        await driver.asyncrun()

Normally this will be awaited together with any other co-routines needed to run your instrument. Making your script executable, and using the above method should allow your driver to work with other parties INDI server software that expect stdin and stdout streams from drivers.

Alternatively, use indipydriver.IPyServer, this listens on the given host and port, to which a client can connect. Multiple drivers can be served, and multiple client connections can be made::

        server = IPyServer(*drivers, host="localhost", port=7624, maxconnections=5)
        await server.asyncrun()

And a further method which also listens on a host and port, but with a single connection only is shown here. It may be useful in some circumstances as it avoids the code associated with IPyServer::

        driver.listen(host="localhost", port=7624)
        await driver.asyncrun()

In both of the above cases you would use indipyclient, or other INDI client, to connect to this port, however note that if your client is running remotely, and you are connecting over a network, then in the above commands "localhost" would need to be changed to the IP address of the servers listening port, or to "0.0.0.0" to listen on all ports.
