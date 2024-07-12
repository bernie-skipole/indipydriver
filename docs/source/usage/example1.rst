.. _example1:

Example1
========

The following example shows a simulated thermostat and heater which maintains a temperature around 15C.

This, and other, example files can be found at:

https://github.com/bernie-skipole/inditest

In this example a NumberVector and NumberMember contain the temperature which is reported to the client::


    import asyncio

    from indipydriver import (IPyDriver, Device,
                              NumberVector, NumberMember,
                              getProperties, IPyServer
                             )

    # Other vectors, members and events are available,
    # this example only imports those used.

    class ThermalControl:
        """This is a simulation containing variables only, normally it
           would control a real heater, and take temperature measurements
           from a sensor."""

        def __init__(self):
            """Set start up values"""
            self.temperature = 20
            self.target = 15
            self.heater = "Off"

        async def run_thermostat(self):
            """This simulates temperature increasing/decreasing, and turns
               on/off a heater if moving too far from the target."""
            while True:
                await asyncio.sleep(2)
                if self.heater == "On":
                    # increasing temperature if the heater is on
                    self.temperature += 0.1
                else:
                    # decreasing temperature if the heater is off
                    self.temperature -= 0.1

                if self.temperature > self.target+0.5:
                    # too hot
                    self.heater = "Off"

                if self.temperature < self.target-0.5:
                    # too cold
                    self.heater = "On"


    class ThermoDriver(IPyDriver):

        """IPyDriver is subclassed here, with methods created to handle incoming events
           and to transmit the temperature to the client"""

        async def rxevent(self, event):
            """On receiving data from the client this is called, and should handle any
               necessary actions.
               The event object has property 'vector' which is the propertyvector being
               updated or requested by the client.
               Different types of event could be produced, in this case only getProperties
               is expected, in which the client is asking for driver information.
               """

            # Using match - case is ideal for this situation,
            # but requires Python v3.10 or later

            match event:
                case getProperties():
                    # this event is raised for each vector when a client wants to learn about
                    # the device and its properties. This getProperties event should always be
                    # handled as all clients normally start by requesting driver properties.
                    # In response, the coroutine event.vector.send_defVector() should be awaited,
                    # which sends the vector definition back to the client
                    await event.vector.send_defVector()


        async def hardware(self):
            """This is a continuously running coroutine which is used
               to transmit the temperature to connected clients."""

            # get the object controlling the instrument, which is available
            # in the named arguments dictionary 'self.driverdata'.
            thermalcontrol = self.driverdata["thermalcontrol"]

            vector = self['Thermostat']['temperaturevector']
            while not self.stop:
                await asyncio.sleep(10)
                # Send the temperature every 10 seconds
                vector['temperature'] = thermalcontrol.temperature
                # and transmit it to the client
                await vector.send_setVector()

    def make_driver():
        "Returns an instance of the driver"

        # Make an instance of the object controlling the instrument
        thermalcontrol = ThermalControl()
        # and a coroutine which will run the instrument
        runthermo = thermalcontrol.run_thermostat()

        # Make a NumberMember holding the temperature value
        temperaturemember = NumberMember( name="temperature",
                                          format='%3.1f', min=-50, max=99,
                                          membervalue=thermalcontrol.temperature )
        # Make a NumberVector instance, containing the member.
        temperaturevector = NumberVector( name="temperaturevector",
                                          label="Temperature",
                                          group="Values",
                                          perm="ro",
                                          state="Ok",
                                          numbermembers=[temperaturemember] )
        # Make a Device with temperaturevector as its only property
        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector] )

        # Create the Driver which will contain this Device, the coroutine needed
        # to run the instrument, and the instrument controlling object
        driver = ThermoDriver( [thermostat],
                               runthermo,
                               thermalcontrol=thermalcontrol )

        # and return the driver
        return driver


    if __name__ == "__main__":

        driver = make_driver()

        server = IPyServer([driver])
        asyncio.run(server.asyncrun())


In summary. You create any objects or functions needed to operate your
hardware, and these can be inserted into the IPyDriver constructor and will be available
in the dictionary of named arguments 'driverdata'.  Any tasks you wish to start together
with the driver can be included in the 'tasks' argument.

You would typically create your own child class of IPyDriver, overriding methods:

**async def rxevent(self, event)**

To handle incoming calls from the client.

Note, in the above example the rxevent only handles the received getProperties event,
which the default rxevent of IPyDriver also does. Therefore in this case it was not necessary
to override this.  It is only done above to illustrate the method.

**async def hardware(self)**

To run a continuous long running loop, typically sending data to the client. Like
all async tasks, this should be non blocking, so typically should include a call
to await asyncio.sleep() in its loop.

Testing self.stop is also useful, as this stop flag is set to True when shutdown() is
called on the driver, and therefore the hardware loop should exit as shown above.

----

The driver can manage multiple devices.

Each device contains one or more vectors.

Each vector contains one or more members which hold instrument values.

Your package should include a make_driver() function which returns the driver
and makes your package suitable for import into other possible python scripts.

Finally, if the driver is to communicate by stdin and stdout::

    if __name__ == "__main__":

        driver = make_driver()
        asyncio.run(driver.asyncrun())

Alternatively, if you want the driver to listen on a port::

    if __name__ == "__main__":

        driver = make_driver()
        server = IPyServer([driver], host="localhost",
                                     port=7624,
                                     maxconnections=5)
        asyncio.run(server.asyncrun())

The server can contain multiple drivers, the first argument to IPyServer is
a list of drivers.

If host, port and maxconnections arguments are not given, the above defaults
are used.
