
import asyncio

from indipydriver import (IPyDriver, Device,
                          NumberVector, NumberMember,
                          getProperties, newNumberVector,
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

    async def rxevent(self, event):
        """On receiving data, this is called, and should handle any necessary actions
           The event object has property 'vector' which is the propertyvector being
           updated or requested by the client.
           """

        thermalcontrol = self.driverdata["thermalcontrol"]

        match event:

            case getProperties():
                await event.vector.send_defVector()

            case newNumberVector(devicename='Thermostat',
                                 vectorname='targetvector') if 'target' in event:
                # Set the received value as the thermostat target
                newtarget = event['target']
                # The self.indi_number_to_float method converts the received string,
                # which may be in a number of formats to a Python float value. This
                # can then be set into thermalcontrol
                try:
                    target = self.indi_number_to_float(newtarget)
                except TypeError:
                    # ignore an incoming invalid number
                    return
                # set new target
                thermalcontrol.target = target
                # and set the new target value into the vector,
                # then transmit the vector back to client.
                event.vector['target'] = target
                await event.vector.send_setVector()


    async def hardware(self):
        """This is a continuously running coroutine which is used
           to transmit the temperature to connected clients."""

        thermalcontrol = self.driverdata["thermalcontrol"]
        vector = self['Thermostat']['temperaturevector']
        while True:
            await asyncio.sleep(10)
            # Send the temperature every 10 seconds
            vector['temperature'] = thermalcontrol.temperature
            # and transmit it to the client
            await vector.send_setVector()


def make_driver():
    "Returns an instance of the driver"

    thermalcontrol = ThermalControl()
    runthermo = thermalcontrol.run_thermostat()

    # create a vector with one number 'temperaturemember' as its member
    temperaturemember = NumberMember( name="temperature",
                                      format='%3.1f', min=-50, max=99,
                                      membervalue=thermalcontrol.temperature )
    temperaturevector = NumberVector( name="temperaturevector",
                                      label="Temperature",
                                      group="Values",
                                      perm="ro",
                                      state="Ok",
                                      numbermembers=[temperaturemember] )

    # create a vector with one number 'targetmember' as its member
    targetmember = NumberMember( name="target",
                                 format='%3.1f', min=-50, max=99,
                                 membervalue=thermalcontrol.target )
    targetvector = NumberVector( name="targetvector",
                                 label="Target",
                                 group="Values",
                                 perm="rw",
                                 state="Ok",
                                 numbermembers=[targetmember] )

    # note the targetvector has permission rw so the client can set it

    # create a device with the two vectors
    thermostat = Device( devicename="Thermostat",
                         properties=[temperaturevector, targetvector] )

    # Create the Driver, containing this Device and instrument
    # controlling objects
    driver = ThermoDriver( devices=[thermostat],
                           tasks=[runthermo],
                           thermalcontrol=thermalcontrol )

    # and return the driver
    return driver


if __name__ == "__main__":

    driver = make_driver()

    server = IPyServer([driver], host="localhost",
                                 port=7624,
                                 maxconnections=5)

    asyncio.run(server.asyncrun())
