# indipydriver

This is a pure python package, with no dependencies, providing a set of classes which can be used to create an INDI driver.

INDI - Instrument Neutral Distributed Interface.

See https://en.wikipedia.org/wiki/Instrument_Neutral_Distributed_Interface

Typically the driver created with this package interfaces between your code which controls an instrument, or GPIO pins on the computer itself, and the INDI protocol which communicates to an INDI client. The protocol defines the format of the data sent, such as light, number, text or switch, and the client can send commands to control the instrument.  The client can be general purpose - communicating with any INDI driver, and taking the format of switches, numbers etc., from the protocol.

INDI is normally used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control providing drivers are available. This package is aimed at making drivers easy to write.

The driver object created contains 'device' objects, each of which can contain 'vector' objects, such as a SwitchVector or LightVector. These Vector objects can contain one or more 'members', such as a number of 'switches', or a number of 'lights'.

Typically you would create a subclass of IPyDriver.

The driver has two methods which should be overwritten.

async def clientevent(self, event)

This is called whenever data is received, the event object describes the received data, and you provide the code which then controls your instrument.

async def hardware(self)

This should be a contuously running coroutine which you can use to poll your instruments, and if required send updates to the client.

Having created your IPyDriver subclass, you would create member objects, being instances of SwitchMember, LightMember, TextMember, BLOBMember or NumberMember which provide attribute values to control your instrument.

You would then create vector objects, being instances of SwitchVector, LightVector, TextVector, BLOBVector or NumberVector these containing the appropriate member objects.

You would then create one or more 'Device' instances, containing the vector objects.

And finally you would create an instance of your IPyDriver subclass, which in turn is set with the Devices.

Finally you would run the driver asyncrun() method which runs the driver, typically called using:

asyncio.run(driver.asyncrun())

The driver can transmit/receive either by stdin/stdout, or by a port, typically localhost:7624 which is the INDI port number, and to which a client typically connects. If this is the only driver on the network, then the 'indiserver' (debian package indi-bin) software - which connects multiple drivers to a port - is not needed.

An INDI web client is available on Pypi as project indiredis, and can connect to port 7624, and display the instrument controls.

Documentation at https://indipydriver.readthedocs.io
