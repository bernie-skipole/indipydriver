# indipydriver

If you are developing a Python project to control some form of instrument, with switches, indicators or measurement data, this package provides classes which can be used to send and receive data on a port. A terminal client can then view the instrument, enabling easy headless control.

The package creates and serves the INDI protocol which is defined so that drivers should operate with any INDI client.

INDI - Instrument Neutral Distributed Interface.

See https://en.wikipedia.org/wiki/Instrument_Neutral_Distributed_Interface

This is one of three associated packages.

**Indipydriver** provides an 'IPyDriver' class to work with your own code to produce the INDI protocol, and an 'IPyServer' class to serve it on a port.

**Indipyterm** is a terminal client, which can be run to view the instrument controls.

Optionally - if you wanted to create dedicated client programs:

**Indipyclient** provides classes which you can use to connect to the port, to create your own client, or to script control of your instrument.

Indipyterm can be remote, or could work on the same machine. As it is a terminal client, it could be run from an SSH connection, conveniently allowing headless operation.

These packages are available on Pypi, and should interwork with other services that follow the INDI specification.

The image below shows the indipyterm terminal connected to a server running an example driver (switching on or off an LED on a RaspberryyPi). The example is described at:

https://indipydriver.readthedocs.io/en/latest/usage/concept.html#first-example


![Terminal screenshot](https://github.com/bernie-skipole/indipydriver/raw/main/docs/source/usage/images/image3.png)


The protocol defines the format of the data sent, such as light, number, text, switch or BLOB (Binary Large Object) and the client can send commands to control the instrument.  The client takes the display format of switches, numbers etc., from the protocol.

INDI is often used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control.

Indipydriver provides classes of 'members', 'vectors' and 'devices', where members hold instrument values, such as switch and number values. Vectors group members together, with labels and group strings, which inform the client how to display the values. 'Devices' hold a number of vectors, so a single device can display several groups of controls.

The 'IPyDriver' class holds one or more devices, and provides methods you can use to send and receive data, which you would use to interface with your own code.

You would create a subclass of IPyDriver and override the following methods.

**async def rxevent(self, event)**

This is automatically called whenever data is received from the client to set an instrument parameter. The event object describes the received data, and you provide the code which then controls your instrument.

**async def hardware(self)**

This is called when the driver starts, and as default does nothing, typically it could be a contuously running coroutine which you can use to operate your instruments, and if required send updates to the client.

**async def snoopevent(self, event)**

This is only used if the device is monitoring (snooping) on other devices.

The indipydriver package also includes an IPyServer class. Having created an instance of your IPyDriver subclass, you would serve this, and any other drivers with an IPyServer object:

    server = IPyServer(*drivers, host="localhost", port=7624, maxconnections=5)
    await server.asyncrun()

A connected client can then control all the drivers.

IPyServer can also run third party INDI drivers created with other languages or tools, using an add\_exdriver method.

## Networked instruments

IPyServer also has an add\_remote method which can be used to add connections to remote servers, creating a tree network of servers.

![INDI Network](https://github.com/bernie-skipole/indipydriver/raw/main/docs/source/usage/images/rem2.png)

With such a layout, the client can control all the instruments.

Documentation at https://indipydriver.readthedocs.io

Installation from https://pypi.org/project/indipydriver

indipyclient available from https://pypi.org/project/indipyclient

indipyterm available from https://pypi.org/project/indipyterm
