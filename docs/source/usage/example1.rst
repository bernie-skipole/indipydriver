Example1
========

The following example shows a simulated thermostat and heater which
maintains a temperature around 15C.

In this example a NumberVector and NumberMember
contains the temperature which is reported to the client::


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
            "Set start up values"
            self.temperature = 20
            self.target = 15
            self.heater = "On"

        # Numbers need to be explicitly set in the indi protocol
        # so the instrument needs to give a string version of numbers

        @property
        def stringtemperature(self):
            "Gives temperature as a string to two decimal places"
            return '{:.2f}'.format(self.temperature)

        def control(self):
            """This simulates temperature increasing/decreasing, and
               turns on/off a heater if moving too far from the target
               temperature. It should be called at regular intervals"""

            if self.heater == "On":
                # increasing temperature if the heater is on
                self.temperature += 0.2
            else:
                # decreasing temperature if the heater is off
                self.temperature -= 0.2

            if self.temperature > self.target+0.5:
                # too hot
                self.heater = "Off"

            if self.temperature < self.target-0.5:
                # too cold
                self.heater = "On"

        async def poll_thermostat(self):
            "poll thermostat control every second"
            while True:
                await asyncio.sleep(1)
                self.control()
                # control is called to turn on and off the heater to
                # keep the temperature near to the target.


    # An instance of the above class will be set as a keyword argument of
    # the driver, and will be available in an attribute dictionary

    class ThermoDriver(IPyDriver):

        """IPyDriver is subclassed here, with two methods created to handle incoming events
           and to control and monitor the instrument hardware"""

        async def clientevent(self, event):
            """On receiving data, this is called, and should handle any necessary actions
               The event object has property 'vector' which is the propertyvector being
               updated or requested by the client.
               Different types of event could be produced, in this case only getProperties
               is expected, in which the client is asking for driver information.
               """

            # note: using match - case is ideal for this situation,
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
            """This is a continuously running coroutine which can be used to run the hardware
               and to keep the temperaturevector updated with the latest temperature."""

            # Get the ThermalControl instance, and run the thermostat polling task
            control = self.driverdata["control"]
            poll_task = asyncio.create_task(control.poll_thermostat())
            # the poll_thermostat method is now running continuously

            # report temperature to the client every ten seconds
            device = self['Thermostat']
            vector = device['temperaturevector']
            while True:
                await asyncio.sleep(10)
                # get the latest temperature, and set it into the vector, then transmit
                # this vector to the client using its send_setVector method
                vector['temperature'] = control.stringtemperature
                await vector.send_setVector(timeout='10')
                # the 'timeout' argument informs the client that this
                # value is only valid for ten seconds


    def make_driver():
        "Uses the above classes to make an instance of the driver"

        # create hardware object
        thermalcontrol = ThermalControl()

        # create a vector with one number 'temperature' as its member

        # Note: numbers must be given as strings
        temperature = NumberMember(name="temperature", format='%3.1f', min='-50', max='99',
                                   membervalue=thermalcontrol.stringtemperature)
        # Create a NumberVector instance, containing the member.
        temperaturevector = NumberVector( name="temperaturevector",
                                          label="Temperature",
                                          group="Values",
                                          perm="ro",
                                          state="Ok",
                                          numbermembers=[temperature] )

        # create a device with temperaturevector as its only property
        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector] )

        # Create the Driver, containing this device and the hardware control object
        driver = ThermoDriver(devices=[thermostat], control=thermalcontrol)

        # and return the driver
        return driver


    if __name__ == "__main__":

        driver = make_driver()

        # In this example, set the driver to listen on a host/port
        # rather than stdin and stdout.
        # If host and port are not specified in this method call,
        # defaults of 'localhost' and 7624 are used
        driver.listen()

        # If the above line is not included, the driver will
        # communicate via stdin and stdout.

        # Finally the driver asyncrun() method is called which runs the driver
        asyncio.run(driver.asyncrun())

        # To see this working, in another terminal try "telnet localhost 7624" and
        # Copy and paste the following xml into the terminal:

        # <getProperties version="1.7" />

        # You should see the vector definition xml returned followed by the
        # temperature being reported every ten seconds.


In summary. You create any objects or functions needed to operate your
hardware, and these can be inserted into the IPyDriver constructor.

You would typically create your own child class of IPyDriver, overiding methods:

async def clientevent(self, event) - to handle incoming calls from the client.

async def hardware(self) - to run any continuous tasks.

You would also create members which contain values to be sent or received from
the client, one or more members are included in vectors.

vectors are included in devices.

devices are included in the driver.

Your package should include a make_driver() function which returns the driver
and makes your package suitable for import into other possible python scripts.

Finally, if the driver is to communicate by stdin and stdout::

    if __name__ == "__main__":

        driver = make_driver()

        asyncio.run(driver.asyncrun())

Alternatively, if you want the driver to listen on a port::

    if __name__ == "__main__":

        driver = make_driver()

        server = IPyServer([driver], maxconnections=5)

        asyncio.run(server.asyncrun())
