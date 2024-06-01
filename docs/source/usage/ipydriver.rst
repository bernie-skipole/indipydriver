IPyDriver
=========

.. autoclass:: indipydriver.IPyDriver
   :members:

----

There are three ways a driver can be run, assuming 'driver' is an instance of this class.

This outputs the xml data on stdout, and reads it on stdin::

        asyncio.run(driver.asyncrun())

Using indipydriver.IPyServer, this listens on the given host and port, to which a client can connect. Multiple drivers can be served, and multiple client connections can be made::

        server = IPyServer([driver], host="localhost", port=7624, maxconnections=5)
        asyncio.run(server.asyncrun())

This also listens on a host and port, but with a single connection only, may be useful for testing as it avoids the code associated with IPyServer::

        driver.listen(host="localhost", port=7624)
        asyncio.run(driver.asyncrun())

The driver is also a mapping, of devicename:deviceobject, so your code in the hardware or rxevent methods could access a specific device using self['devicename'].

Similarly a Device object is a mapping to a vector, so to access a vector you could use self['devicename']['vectorname'].

The 'snooping' capabilities enable one driver to receive data transmitted by another, possibly remote driver. For a simple instrument this will probably not be used.


Logging
=======

This indipydriver package uses the Python standard library logging module, it uses logger with name "indipydriver" and emits logs at levels:

**ERROR**

Logs errors including tracebacks from exceptions

**INFO**

Logs informational messages and error messages as above.

**DEBUG**

Logs xml data transmitted and received by each driver, and the info and error messages as above. The logs of BLOB tags do not include contents.

The driver has attribute self.debug_enable, which defaults to True.

If multiple drivers are in use, and possibly snooping on each other, then in DEBUG mode, this may result in duplicate xml logs, transmitted by one driver and received by another. In which case setting debug_enable to False on drivers you are not interested in, will help isolate just your desired logs.

As default, only the logging.NullHandler() is added, so no logs are generated. To create logs you will need to add a handler, and a logging level, for example::

    import logging
    logger = logging.getLogger('indipydriver')

    fh = logging.FileHandler("logfile.log")
    logger.addHandler(fh)

    logger.setLevel(logging.DEBUG)

This leaves you with the flexibility to add any available loghandler, and to set your own formats if required.
