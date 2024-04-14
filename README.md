# indipydriver

This is a pure python package, with no dependencies, providing a set of classes which can be used to create an INDI driver and serve the INDI communications protocol on a port.

INDI - Instrument Neutral Distributed Interface.

See https://en.wikipedia.org/wiki/Instrument_Neutral_Distributed_Interface

Typically the driver created with this package interfaces between your code which controls an instrument, or GPIO pins on the computer itself, and the INDI protocol which communicates to an INDI client.

This package can be used to create the drivers, it does not include client functions. The INDI protocol is defined so that drivers should operate with any INDI client.

This is a companion package to 'indipyclient' which provides a terminal client.

The protocol defines the format of the data sent, such as light, number, text or switch, and the client can send commands to control the instrument.  The client can be general purpose, taking the format of switches, numbers etc., from the protocol.

INDI is often used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control providing drivers are available.

The driver object created contains 'device' objects, each of which can contain 'vector' objects, such as a SwitchVector or LightVector. These Vector objects can contain one or more 'members', such as a number of 'switches', or a number of 'lights'.

Typically you would create a subclass of IPyDriver.

The driver has methods which should be overwritten.

async def clientevent(self, event)

This is called whenever data is received from the client, typically to set an instrument parameter. The event object describes the received data, and you provide the code which then controls your instrument.

async def hardware(self)

This should be a contuously running coroutine which you can use to operate your instruments, and if required send updates to the client.

async def snoopevent(self, event)

This is only used if the device is monitoring (snooping) on other devices.

Having created an instance of your IPyDriver subclass, you would serve this, and any other drivers with an IPyServer object::

    server = IPyServer([driver], host="localhost", port=7624, maxconnections=5)
    asyncio.run(server.asyncrun())

A connected client can then control all the drivers.

Documentation at https://indipydriver.readthedocs.io

Installation from https://pypi.org/project/indipydriver
