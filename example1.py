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

    """IPyDriver is subclassed here, with two methods created to handle incoming events
       and to transmit the temperature to the client"""

    async def clientevent(self, event):
        """On receiving data, this is called, and should handle any necessary actions
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

        thermalcontrol = self.driverdata["thermalcontrol"]
        vector = self['Thermostat']['temperaturevector']
        while True:
            await asyncio.sleep(10)
            # Send the temperature every 10 seconds
            # Numbers need to be explicitly set in the indi protocol
            # so need to set a string version into the vector
            vector['temperature'] = str(thermalcontrol.temperature)
            # and transmit it to the client
            await vector.send_setVector()

def make_driver():
    "Returns an instance of the driver"

    thermalcontrol = ThermalControl()

    # create a vector with one number 'temperaturemember' as its member

    # Note: numbers must be given as strings
    stringtemperature = str(thermalcontrol.temperature)

    temperaturemember = NumberMember( name="temperature",
                                      format='%3.1f', min='-50', max='99',
                                      membervalue=stringtemperature )
    # Create a NumberVector instance, containing the member.
    temperaturevector = NumberVector( name="temperaturevector",
                                      label="Temperature",
                                      group="Values",
                                      perm="ro",
                                      state="Ok",
                                      numbermembers=[temperaturemember] )

    # create a device with temperaturevector as its only property
    thermostat = Device( devicename="Thermostat",
                         properties=[temperaturevector] )

    # set the coroutine to be run with the driver
    runthermo = thermalcontrol.run_thermostat()

    # Create the Driver, containing this device and
    # the coroutine needed to run the instrument
    driver = ThermoDriver( devices=[thermostat],
                           tasks=[runthermo],
                           thermalcontrol=thermalcontrol )

    # and return the driver
    return driver


if __name__ == "__main__":

    driver = make_driver()

    server = IPyServer([driver])
    asyncio.run(server.asyncrun())

    # To see this working, in another terminal try "telnet localhost 7624" and
    # Copy and paste the following xml into the terminal:

    # <getProperties version="1.7" />

    # You should see the vector definition xml returned followed by the
    # temperature being reported every ten seconds.

