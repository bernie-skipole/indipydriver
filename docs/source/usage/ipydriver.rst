IPyDriver
=========

.. autoclass:: indipydriver.IPyDriver
   :members:

There are three ways a driver can be run, assuming 'driver' is an instance of this class.

This outputs the xml data on stdout, and reads it on stdin::

        asyncio.run(driver.asyncrun())

This listens on the given host and port, to which a client can connect. Multiple drivers can be served, and multiple client connections can be made::

        server = IPyServer([driver], host="localhost", port=7624, maxconnections=5)
        asyncio.run(server.asyncrun())

This also listens on a host and port, but with a single connection only, may be useful for testing as it avoids the code associated with IPyServer::

        driver.listen(host="localhost", port=7624)
        asyncio.run(driver.asyncrun())

The driver is also a mapping, of devicename:deviceobject, so your code in the hardware or clientevent methods could access a specific device using self['devicename'].

Similarly a Device object is a mapping to a vector, so to access a vector you could use self['devicename']['vectorname'].

The 'snooping' capabilities enable one driver to receive data transmitted by another, possibly remote driver. For a simple instrument this will probably not be used.
