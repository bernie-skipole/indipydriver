IPyDriver
=========

The driver object is a mapping, of devicename:deviceobject, so your code in the hardware or rxevent methods could access a specific device using self['devicename'].

Similarly a Device object is a mapping to a vector, so to access a vector you could use self['devicename']['vectorname'].

The 'snooping' capabilities enable one driver to receive data transmitted by another, possibly remote driver. For a simple instrument this will probably not be used.

----

.. autoclass:: indipydriver.IPyDriver
   :members:

----

There are three ways a driver can be run, assuming 'driver' is an instance of this class.

This outputs the xml data on stdout, and reads it on stdin::

        asyncio.run(driver.asyncrun())

Making your script executable, and using the above method should allow your driver to work with other parties INDI server software.

Alternatively, use indipydriver.IPyServer, this listens on the given host and port, to which a client can connect. Multiple drivers can be served, and multiple client connections can be made::

        server = IPyServer([driver], host="localhost", port=7624, maxconnections=5)
        asyncio.run(server.asyncrun())

And a further method which also listens on a host and port, but with a single connection only is shown here. It may be useful in some circumstances as it avoids the code associated with IPyServer::

        driver.listen(host="localhost", port=7624)
        asyncio.run(driver.asyncrun())

Typically you would use indipyclient to connect to this port, however note that if indipyclient is running remotely, and you are connecting over a network, then in the above commands "localhost" would need to be changed to the IP address of the servers listening port, or to "0.0.0.0" to listen on all ports.
