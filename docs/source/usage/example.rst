Example
=======

An example driver - controlling a simulated thermostat is shown::

    import asyncio

    from indipydriver import (IPyDriver, Device,
                              NumberVector, NumberMember,
                              getProperties, newNumberVector
                             )


    # Other vectors, members and events are available, this example only imports those used.

    # Simulate a heater, temperature sensor, and a target temperature

    class ThermalControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set start up values"
            self.temperature = 20
            self.target = 15
            self.heater = "On"

        # Numbers need to be explicitly set in the indi protocol
        # so the instrument needs to give a string version of numbers

        @property
        def stringtemperature(self)
            "Gives temperature as a string to two decimal places"
            return '{:.2f}'.format(self.temperature)

        @property
        def stringtarget(self)
            "Gives target as a string to two decimal places"
            return '{:.2f}'.format(self.target)

        def control(self):
            """This simulates temperature increasing/decreasing, and
               turns on/off a heater if moving too far from the target temperature
               Should be called at regular intervals"""

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
            "poll thermostat every second"
            while True:
                await asyncio.sleep(1)
                # the control function turns on and off the heater to keep
                # the temperature near to the target.
                self.control()



    class ThermoDriver(IPyDriver):

        """IPyDriver is subclassed here, with two methods created to handle incoming events
           and to control and monitor the instrument hardware"""

        async def clientevent(self, event):
            """On receiving data, this is called, and should handle any necessary actions
               The event object has property 'vector' which is the propertyvector being
               updated by the client.
               Different types of event could be produced, in this case only two are expected,
               getProperties, in which the client is asking for driver information, and
               newNumberVector, in which case the client is setting a target temperature.
               """
            await asyncio.sleep(0)
            # note: using match - case is ideal for this situation,
            # but requires Python v3.10 or later

            # The hardware control object is stored in the driverdata dictionary
            control = self.driverdata["control"]

            match event:
                case getProperties():
                    # this event is raised for each vector when a client wants to learn about
                    # the device and its properties. The event has attribute 'vector' which is
                    # the vector object being requested. This event should always be handled
                    # as all clients normally start by requesting driver properties.
                    # vector.send_defVector() should be called, which sends the vector
                    # definition to the client
                    await event.vector.send_defVector()
                case newNumberVector(devicename='Thermostat', vectorname='targetvector'):
                    # this event maps the member name to value as a number string
                    # So set the received value as the thermostat target
                    # and also set it into the vector, and send it back to the client
                    # so this new target can be displayed by the client
                    if 'target' in event:
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
                # get the latest temperature, and set it into the vector
                vector['temperature'] = control.stringtemperature
                await vector.send_setVector(timeout='10')
                # the 'timeout' argument informs the client that this
                # value is only valid for ten seconds


    def make_driver():
        "Creates the driver"

        # create hardware object
        thermalcontrol = ThermalControl()

        # create a vector with one number 'temperature' as its member
        # Note: vector members require numbers to be given as strings
        temperature = NumberMember(name="temperature", format='%3.1f', min='-50', max='99',
                                   membervalue=thermalcontrol.stringtemperature)
        # set this member into a vector, this is read only
        temperaturevector = NumberVector( name="temperaturevector",
                                          label="Temperature",
                                          group="Values",
                                          perm="ro",
                                          state="Ok",
                                          numbermembers=[temperature] )

        # create a vector with one number 'target' as its member
        target = NumberMember(name="target", format='%3.1f', min='-50', max='99',
                              membervalue=thermalcontrol.stringtarget)
        # set this member into a vector, this is read-write
        targetvector = NumberVector( name="targetvector",
                                     label="Target",
                                     group="Values",
                                     perm="rw",
                                     state="Ok",
                                     numbermembers=[target] )

        # create a device with the above two vectors as its properties
        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector, targetvector] )

        # Create the Driver, containing this device, and the hardware control object
        driver = ThermoDriver(devices=[thermostat],  control=thermalcontrol)

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

        # and finally the driver asyncrun() method is called which runs the driver
        asyncio.run(driver.asyncrun())

        # to see this working, in another terminal try "telnet localhost 7624" and
        # you should see the xml string of the temperature being reported every ten seconds.

        # Copy and paste the following xml into the terminal:

        # <getProperties version="1.7" />

        # This simulates a client asking for the driver properties, their definitions should
        # be returned by the driver.
        # To set a new target temperature, paste the following:

        # <newNumberVector device="Thermostat" name="targetvector"><oneNumber name="target">40</oneNumber></newNumberVector>

        # this simulates a client setting a target temperature of 40 degrees.
        # Every ten seconds you should see xml from the driver showing the
        # temperature changing towards the target.


The above sets two vectors into a single device, and each vector only has one member. The 'vector' is the unit of data transmitted, so if a vector has multiple members, this ensures all those member values are updated together.
