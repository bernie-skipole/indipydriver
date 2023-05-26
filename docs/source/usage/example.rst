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

    TEMPERATURE = 20

    TARGET = 15

    HEATER = "On"

    def control():
        """this simulates temperature increasing/decreasing, and
           turns on/off a heater if moving too far from the target temperature
           Should be called at regular intervals"""

        global TEMPERATURE, HEATER

        if HEATER == "On":
            # increasing temperature if the heater is on
            TEMPERATURE += 0.2
        else:
            # decreasing temperature if the heater is off
            TEMPERATURE -= 0.2

        if TEMPERATURE > TARGET+0.5:
            # too hot
            HEATER = "Off"

        if TEMPERATURE < TARGET-0.5:
            # too cold
            HEATER = "On"


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
            global TARGET
            await asyncio.sleep(0)
            # note: using match - case is ideal for this situation,
            # but requires Python v3.10 or later
            match event:
                case getProperties():
                    # this event is raised for each vector when a client wants to learn about
                    # the device and its properties. The event has attribute 'vector' which is
                    # the vector object being requested. This event should always be handled
                    # as all clients normally start by requesting driver properties.
                    # vector.send_defVector() should be called, which sends the vector
                    # definition to the client
                    event.vector.send_defVector()
                case newNumberVector(devicename='Thermostat', vectorname='targetvector'):
                    # this event maps the member name to value as a number string
                    # So set the received value as the thermostat target
                    # and also set it into the vector, and send it back to the client
                    # so this new target can be displayed by the client
                    if 'target' in event:
                        newtarget = event['target']
                        # The self.indi_number_to_float method converts the received string,
                        # which may be in a number of formats to a Python float value. This
                        # is set into global value TARGET, which, in this simulation, is
                        # used by the control function to control the heater
                        TARGET = self.indi_number_to_float(newtarget)
                        # and set the new target value into the vector member, then
                        # transmits the vector back to client, with vector state ok
                        event.vector['target'] = newtarget
                        # vector.state can be one of 'Idle','Ok','Busy' or 'Alert'
                        # sending 'Ok' informs the client that the value has been received
                        event.vector.state = 'Ok'
                        event.vector.send_setVector()

        async def hardware(self):
            """This coroutine controls and monitors the instrument, and if required
               sends updates to the client"""
            device = self['Thermostat']
            temperaturevector = device['temperaturevector']
            # and gather async functions which poll the hardware and
            # sends updates to the client
            await asyncio.gather(  poll_thermostat(temperaturevector),
                                   send_update(temperaturevector)  )


    # the above driver calls on these two coroutines to control and
    # read the instrument hardware

    async def poll_thermostat(vector):
        "poll thermostat every second, places current value into the vector"
        while True:
            await asyncio.sleep(1)
            # the control function turns on and off the heater to keep
            # the temperature near to the target.
            control()
            # and as this measures the temperature, update the vector
            # member with the current TEMPERATURE global value
            vector["temperature"] = TEMPERATURE
            # but no need to send this vector to the client at this point
            # as client updates are not needed every second.
            # Client updates are done every 10 seconds by the
            # send_update coroutine.

    async def send_update(vector):
        """This sends the current temperature in
           the given vector every ten seconds"""
        while True:
            await asyncio.sleep(10)
            vector.send_setVector(timeout=10)
            # the 'timeout' argument informs the client that this
            # value is only valid for ten seconds

    def make_driver():
        "Creates the driver"

        # create a vector with one number 'temperature' as its member
        temperature = NumberMember(name="temperature", format='%3.1f', min=-50, max=99)
        # set this member into a vector
        temperaturevector = NumberVector( name="temperaturevector",
                                          label="Temperature",
                                          group="Values",
                                          perm="ro",
                                          state="Ok",
                                          numbermembers=[temperature] )
        # and set the member value
        temperaturevector["temperature"] = TEMPERATURE

        # create a vector with one number 'target' as its member
        target = NumberMember(name="target", format='%3.1f', min='7', max='40')
        # set this member into a vector
        targetvector = NumberVector( name="targetvector",
                                     label="Target",
                                     group="Values",
                                     perm="rw",
                                     state="Ok",
                                     numbermembers=[target] )
        # and set the member value
        targetvector["target"] = TARGET

        # create a device with the above two vectors as its properties
        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector, targetvector] )

        # Create the Driver, containing this device
        driver = ThermoDriver(devices=[thermostat])

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
