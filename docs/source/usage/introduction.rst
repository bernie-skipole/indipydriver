Introduction
============


indipydriver
^^^^^^^^^^^^

If you are developing a Python project to control some form of instrument, with switches, indicators or measurement data, this package provides classes which can be used to send and receive data on a port.

The package creates and serves the INDI protocol which is defined so that drivers should operate with any INDI client.

For further information on INDI, see :ref:`references`.

Typically you would use this package to create drivers to control an instrument, or GPIO pins on the computer itself, and the package functions generate the INDI protocol which communicates to an INDI client.

This is one of three associated packages.

Indipydriver provides an 'IPyDriver' class to work with your own code to produce the INDI protocol, and an 'IPyServer' class to serve it on a port.

Indipyclient provides classes which you can use to connect to the port, to create your own client, or to script control of your instrument.

Indipyterm is a terminal client, which can be run to view the instrument controls.

Indipyterm can be remote, or could work on the same machine. As it is a terminal client, it could be run from an SSH connection, conveniently allowing headless operation.

These packages are available on Pypi, and should interwork with other services that follow the INDI specification.

INDI is often used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control if appropriate drivers are written.

The package can be installed from:

https://pypi.org/project/indipydriver

Typically you would create a subclass of IPyDriver.

The driver has methods which can be overwritten.

**async def rxevent(self, event)**

This is called whenever data is received from the client, typically to set an instrument parameter. The event object describes the received data, and you provide the code which then controls your instrument.

**async def hardware(self)**

This can be a contuously running coroutine which you can use to operate your instruments, and if required send updates to the client.

**async def snoopevent(self, event)**

This is only used if the device is monitoring (snooping) on other devices.

The indipydriver package also includes an IPyServer class. Having created an instance of your IPyDriver subclass, you would serve this, and any other drivers with an IPyServer object::

    server = IPyServer(*drivers, host="localhost", port=7624, maxconnections=5)
    await server.asyncrun()

A connected client, such as indipyterm, can then control all the drivers.

The IPyServer can also run third party INDI drivers created with other languages or tools, using an add_exdriver method. It also has an add_remote method which can be used to add connections to remote servers, creating a tree network of servers.
