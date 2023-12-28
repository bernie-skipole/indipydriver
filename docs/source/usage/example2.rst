Example2
========

This example shows how the client can set a target temperature by sending
a 'newNumberVector', which causes the clientevent method to be called::

    import asyncio

    from indipydriver import (IPyDriver, Device,
                              NumberVector, NumberMember,
                              getProperties, newNumberVector,
                              IPyServer
                             )


    class ThermalControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set start up values"
            self.temperature = 20
            self.target = 15
            self.heater = "On"

        @property
        def stringtemperature(self):
            "Gives temperature as a string to two decimal places"
            return '{:.2f}'.format(self.temperature)

        @property
        def stringtarget(self):
            "Gives target as a string to two decimal places"
            return '{:.2f}'.format(self.target)

        async def poll_thermostat(self):
            """This simulates temperature increasing/decreasing, and turns
               on/off a heater if moving too far from the target."""
            while True:
                await asyncio.sleep(1)
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


    class ThermoDriver(IPyDriver):

        """IPyDriver is subclassed here, with two methods created to handle incoming events
           and to control and monitor the instrument hardware"""

        async def clientevent(self, event):
            """On receiving data, this is called, and should handle any necessary actions,
               in this case only two are expected; getProperties, in which the client is
               asking for driver information, and newNumberVector, in which case the client
               is setting a target temperature.
               """

            # The hardware control object is stored in the driverdata dictionary
            control = self.driverdata["control"]

            match event:
                case getProperties():
                    await event.vector.send_defVector()
                case newNumberVector(devicename='Thermostat',
                                     vectorname='targetvector') if 'target' in event:
                    # Set the received value as the thermostat target and also set
                    # it into the vector, and send it back to the client
                    newtarget = event['target']
                    # The self.indi_number_to_float method converts the received string,
                    # which may be in a number of formats to a Python float value. This
                    # is set into the ThermalControl object
                    try:
                        target = self.indi_number_to_float(newtarget)
                    except TypeError:
                        # ignore an incoming invalid number
                        pass
                    else:
                        # set this new target into the ThermalControl object
                        control.target = target
                        # and set the new target value into the vector member, then
                        # transmits the vector back to client, with vector state ok
                        event.vector['target'] = control.stringtarget
                        # vector.state can be one of 'Idle','Ok','Busy' or 'Alert'
                        # sending 'Ok' informs the client that the value has been received
                        event.vector.state = 'Ok'
                        await event.vector.send_setVector()

        async def hardware(self):
            "Run the hardware"
            # run the thermostat polling task
            control = self.driverdata["control"]
            poll_task = asyncio.create_task(control.poll_thermostat())

            # report temperature every ten seconds
            device = self['Thermostat']
            vector = device['temperaturevector']
            while True:
                await asyncio.sleep(10)
                vector['temperature'] = control.stringtemperature
                await vector.send_setVector(timeout='10')


    def make_driver():
        "Creates the driver"

        # create hardware object
        thermalcontrol = ThermalControl()

        # Create a vector with one number 'temperature' as its member
        temperature = NumberMember(name="temperature", format='%3.1f', min='-50', max='99',
                                   membervalue=thermalcontrol.stringtemperature)
        temperaturevector = NumberVector( name="temperaturevector",
                                          label="Temperature",
                                          group="Values",
                                          perm="ro",
                                          state="Ok",
                                          numbermembers=[temperature] )

        # create a vector with one number 'target' as its member
        target = NumberMember(name="target", format='%3.1f', min='-50', max='99',
                              membervalue=thermalcontrol.stringtarget)
        targetvector = NumberVector( name="targetvector",
                                     label="Target",
                                     group="Values",
                                     perm="rw",
                                     state="Ok",
                                     numbermembers=[target] )

        # create a device with the above two vectors as its properties
        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector, targetvector] )

        # Create the Driver, containing this device and the hardware control object
        driver = ThermoDriver(devices=[thermostat],  control=thermalcontrol)

        # and return the driver
        return driver


    if __name__ == "__main__":

        driver = make_driver()

        # In this example, the driver communicates by stdin and stdout.

        asyncio.run(driver.asyncrun())

        # Call this script, and when running copy and paste the
        # following xml into the terminal:

        # <getProperties version="1.7" />

        # To set a new target temperature, paste the following:

        # <newNumberVector device="Thermostat" name="targetvector"><oneNumber name="target">40</oneNumber></newNumberVector>

        # this simulates a client setting a target temperature of 40 degrees.
        # Every ten seconds you should see xml from the driver showing the
        # temperature changing towards the target.
