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
                              IPyServer
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
            self.stop = False

        def shutdown(self):
            self.stop = True

        async def run_thermostat(self):
            """This simulates temperature increasing/decreasing, and turns
               on/off a heater if moving too far from the target."""
            while not self.stop:
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

        """IPyDriver is subclassed here, with a hardware method
           overridden to transmit the temperature to the client"""

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


    def make_driver(thermalcontrol):
        "Returns an instance of the driver"

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

        # Create the Driver which will contain this Device,
        #  and the instrument controlling object
        driver = ThermoDriver( thermostat,
                               thermalcontrol=thermalcontrol )

        # and return the driver
        return driver


    async def main(thermalcontrol, server):
        "Run the instrument and the server async tasks"
        await asyncio.gather(thermalcontrol.run_thermostat(),
                             server.asyncrun() )


    if __name__ == "__main__":

        # Make an instance of the object controlling the instrument
        thermalcontrol = ThermalControl()
        # make a driver for the instrument
        thermodriver = make_driver(thermalcontrol)
        # and a server, which serves this driver
        server = IPyServer(thermodriver)
        # and run them together
        asyncio.run( main(thermalcontrol, server) )


In summary. You create any objects needed to operate your hardware,
and these can be inserted into the IPyDriver constructor and will be available
in the dictionary of named arguments 'driverdata'.

You would typically create your own child class of IPyDriver, overriding methods:

**async def rxevent(self, event)**

To handle incoming calls from the client.

Note, in the above example the client only reads the temperature and does not send
any data to set it, so it was not necessary to create this method.

**async def hardware(self)**

This runs when the driver or server asyncrun() method is called and is typically
used to run a continuous long running task to send data to the client. Like
all async tasks, this should be non blocking, so generally should include a call
to await asyncio.sleep() in its loop.

Testing self.stop is also useful, as this stop flag is set to True when shutdown() is
called on the driver, and would therefore stop this hardware while loop.

You would then create the IPyServer object to serve the driver, and run the server.asyncrun()
co-routine together with any other tasks needed to run your instrument.

----

The driver can manage multiple devices.

Each device contains one or more vectors.

Each vector contains one or more members which hold instrument values.

It is a good idea to keep the functionality of the instrument and driver separate, so
the instrument can keep running even if there is no driver or server connections.
