# indipydriver

This is a pure python package providing a set of classes which can be used to create an INDI driver.

Typically the driver created with this package would control an instrument, either an instrument connected to the computer, or interfaces, such as GPIO pins on the computer itself.

The driver encapsulates data in the INDI protocol, which communicates to an INDI client. The protocol defines the format of the data sent, such as light, number, text or switch, and the client can send commands to control the instrument.

INDI is normally used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control.

The python driver object created contains 'device' objects, each of which can contain 'vector' objects, such as a SwitchVector or LightVector. These Vector objects can contain one or more 'members', such as a number of 'switches', or a number of 'lights'.

Typically you would create a subclass of IPyDriver.

The driver has two methods which should be overwritten.

async def clientevent(self, event)

This is called whenever data is received, the event object describes the received data, and you provide the code which then controls your instrument.

async def hardware(self)

This should be a contuously running awaitable which you can use to poll your instruments, and if required send updates to the client.

Having created your IPyDriver subclass, you would create member objects, being instances of SwitchMember, LightMember, TextMember, BLOBMember or NumberMember which you create as needed to control your instrument.

You would then create vector objects, being instances of SwitchVector, LightVector, TextVector, BLOBVector or NumberVector these containing the appropriate member objects.

You would then create one or more 'Device' instances, containing the vector objects.

And finally you would create an instance of your IPyDriver subclass, which in turn is set with the Devices.

Finally you would run the driver asyncrun() method which runs the driver, typically called using the asyncio.run() command.

The documentation gives the details of these classes, and methods which can be called to transmit and receive the control data.
