IPyDriver
=========

The driver object is a mapping, of devicename:deviceobject, so your code in the hardware or rxevent methods could access a specific device using self['devicename'].

Similarly a Device object is a mapping to a vector, so to access a vector you could use self['devicename']['vectorname'].

The 'snooping' capabilities enable one driver to receive data transmitted by another, possibly remote driver. For a simple instrument this will probably not be used.

----

.. autoclass:: indipydriver.IPyDriver
   :members:

----

The ipydriver object has attributes:

self.driverdata - The dictionary of named arguments you have optionally set in the constructor

self.stop - This is set to True when the driver.shutdown() method is called.

self.stopped - An asyncio.Event() object, await driver.stopped.wait() will block until the driver stops.

self.debug_enable - As default is set to True, indicating this driver will log xml traffic at level DEBUG.

If self.debug_enable is set to False, then xml traffic will not be logged, this could be useful if you have a number of drivers operating, and you only want one to log xml traffic.

----

There are three ways a driver can be run, assuming 'driver' is an instance of this class.

This coroutine outputs the xml data on stdout, and reads it on stdin::

        await driver.asyncrun()

Normally this will be awaited together with any other co-routines needed to run your instrument. Making your script executable, and using the above method should allow your driver to work with other parties INDI server software that expect stdin and stdout streams from drivers.

Alternatively, use indipydriver.IPyServer, this listens on the given host and port, to which a client can connect. Multiple drivers can be served, and multiple client connections can be made::

        server = IPyServer(driver, host="localhost", port=7624, maxconnections=5)
        await server.asyncrun()

And a further method which also listens on a host and port, but with a single connection only is shown here. It may be useful in some circumstances as it avoids the code associated with IPyServer::

        driver.listen(host="localhost", port=7624)
        await driver.asyncrun()

In both of the above cases you would use indipyclient, or other INDI client, to connect to this port, however note that if your client is running remotely, and you are connecting over a network, then in the above commands "localhost" would need to be changed to the IP address of the servers listening port, or to "0.0.0.0" to listen on all ports.
