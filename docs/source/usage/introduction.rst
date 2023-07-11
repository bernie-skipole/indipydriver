Introduction
============


indipydriver
^^^^^^^^^^^^

This is a pure python package, with no dependencies, providing a set of classes which can be used to create an INDI driver.

INDI - Instrument Neutral Distributed Interface.

For further information on INDI, see :ref:`references`.

Typically the driver created with this package interfaces between your code which controls an instrument, or GPIO pins on the computer itself, and the INDI protocol which communicates to an INDI client.

This package can be used to create the drivers, it does not include client functions. The INDI protocol is defined so that drivers should operate with any INDI client.

The protocol defines the format of the data sent, such as light, number, text or switch, and the client can send commands to control the instrument.  The client can be general purpose, taking the format of switches, numbers etc., from the protocol.

INDI is often used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control providing drivers are available.

The driver object created contains 'device' objects, each of which can contain 'vector' objects, such as a SwitchVector or LightVector. These Vector objects can contain one or more 'members', such as a number of 'switches', or a number of 'lights'.

The package can be installed from:

https://pypi.org/project/indipydriver

Typically you would create a subclass of IPyDriver.

The driver has methods which should be overwritten.

async def clientevent(self, event)

This is called whenever data is received from the client, typically to set an instrument parameter. The event object describes the received data, and you provide the code which then controls your instrument.

async def hardware(self)

This should be a contuously running coroutine which you can use to operate your instruments, and if required send updates to the client.

async def snoopevent(self, event)

This is only used if one device is monitoring (snooping) on other devices, an example is given further in this documentation.

Having created an instance of your IPyDriver subclass, you would run the driver using:

asyncio.run(driver.asyncrun())

The driver can transmit/receive either by stdin/stdout, or by a port.

A further class provided in the package, IPyServer can operate with multiple driver instances, and serves them all via a port, a connected client can then control all the drivers.


Issues
^^^^^^

Using stdin/stdout has required some linux/unix specific commands, which will probably not work on Windows. However setting the driver to listen on a port, or using IPyServer should work on Windows, but is untested. (I don't have a Windows machine.)

When transmitting or receiving BLOBS the entire BLOB is loaded into memory, which may cause issues if the BLOB is large. It is suggested that very large binary objects should be transferred by some other method.
