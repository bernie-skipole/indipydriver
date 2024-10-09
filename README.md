# indipydriver

If you are developing a Python project to operate some form of instrument, with switches, indicators or measurement data, this package can be used to send and receive data on a port to control your instrument.

Indipydriver is a pure python package and has no dependencies.

The package creates and serves the INDI protocol.

INDI - Instrument Neutral Distributed Interface.

See https://en.wikipedia.org/wiki/Instrument_Neutral_Distributed_Interface

The INDI protocol is defined so that drivers should operate with any INDI client.

An associated terminal client indipyclient is available, which connects to the port, so the instrument can be viewed and controlled from a terminal session.

Indipyclient can be remote, or could work on the same machine. As it is a terminal client, it could be run from an SSH connection, conveniently allowing headless operation.

Both indipydriver and indipyclient are available on Pypi, and should interwork with other services that follow the INDI specification.

The image below shows the indipyclient terminal connected to a server running an example driver (switching on or off an LED on a RaspberryyPi). The example is described at:

https://indipydriver.readthedocs.io/en/latest/usage/summary.html


![Terminal screenshot](https://github.com/bernie-skipole/indipydriver/raw/main/docs/source/usage/images/led.png)


The protocol defines the format of the data sent, such as light, number, text, switch or BLOB (Binary Large Object) and the client can send commands to control the instrument.  The client takes the display format of switches, numbers etc., from the protocol.

INDI is often used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control.

Typically you would create a subclass of IPyDriver.

The driver has methods which should be overwritten.

**async def rxevent(self, event)**

This is called whenever data is received from the client, typically to set an instrument parameter. The event object describes the received data, and you provide the code which then controls your instrument.

**async def hardware(self)**

This could be a contuously running coroutine which you can use to operate your instruments, and if required send updates to the client.

**async def snoopevent(self, event)**

This is only used if the device is monitoring (snooping) on other devices.

The indipydriver package also includes an IPyServer class. Having created an instance of your IPyDriver subclass, you would serve this, and any other drivers with an IPyServer object:

    server = IPyServer(driver, host="localhost", port=7624, maxconnections=5)
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
