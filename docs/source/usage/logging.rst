Logging
=======

This indipydriver package uses the Python standard library logging module, and emits logs at levels:

**ERROR**

Logs errors including tracebacks from exceptions

**INFO**

Logs informational messages and error messages as above.

**DEBUG**

Logs xml data transmitted and received, and the info and error messages as above. The logs of BLOB tags do not include contents.

The package uses two loggers with names "indipydriver" and "indipyclient".

The "indipydriver" logger logs driver data, the "indipyclient" logger logs remote server connections data, this because IPyServer is acting as a client when connecting to a remote server.

To create logs from both loggers in a single file you could add a handler and a logging level to the 'root' logger, for example::

    import logging
    logger = logging.getLogger()

    fh = logging.FileHandler("logfile.log")
    logger.addHandler(fh)

    logger.setLevel(logging.DEBUG)

This leaves you with the flexibility to add any available loghandler, and to set your own formats if required.

If you want to add a file handler to "indipydriver" and another to "indipyclient" to log to two different files you would need to obtain the two loggers rather than the root logger::

     driverlogger = logging.getLogger("indipydriver")
     remotelogger = logging.getLogger("indipyclient")

You could then add file handlers and set logging levels to each logger separately.

If you are running multiple drivers, and multiple remote connections, then logged xml traffic may become confusing. To aid this, drivers have attribute self.debug_enable, if only one driver has this set to True, then only the one driver will have its traffic logged.

Similarly the IPyServer add_remote method has a debug_enable argument which can be used to limit logged traffic to a single remote connection.
