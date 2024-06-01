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
