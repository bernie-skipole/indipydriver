Example2
========

This example shows how the client can set a target temperature by sending
a 'newNumberVector', which causes the clientevent method to be called::

    import asyncio

    from datetime import datetime, timezone

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

        def __init__(self, txque):
            """Set start up values, txque is an asyncio.Queue object
               used to transmit temperature readings """
            self.temperature = 20
            self.target = 15
            self.heater = "Off"
            self.txque = txque


        async def poll_thermostat(self):
            """This simulates temperature increasing/decreasing, and turns
               on/off a heater if moving too far from the target."""
            while True:
                await asyncio.sleep(10)
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

                # transmit the temperature and timestamp back to the client
                timestamp = datetime.now(tz=timezone.utc)
                senddata = (timestamp, self.temperature)
                try:
                    self.txque.put_nowait(senddata)
                except asyncio.QueueFull:
                    # if the queue is full, perhaps due to
                    # communications problems, simply drop the
                    # record, but keep operating the thermostat
                    pass


    class ThermoDriver(IPyDriver):
        """IPyDriver is subclassed here, with two methods created to handle incoming events
           and to transmit the temperature to the client"""

        async def clientevent(self, event):
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
                        pass
                    else:
                        # set new target
                        thermalcontrol.target = target
                        # and set the new target value into the vector member,
                        # then transmit the vector back to client.
                        event.vector['target'] = '{:.2f}'.format(target)
                        await event.vector.send_setVector()


        async def hardware(self):
            """This is a continuously running coroutine which is used
               to transmit the temperature to connected clients."""

            txque = self.driverdata["txque"]
            vector = self['Thermostat']['temperaturevector']
            while True:
                # wait until an item is available in txque
                timestamp,temperature = await txque.get()
                # Numbers need to be explicitly set in the indi protocol
                # so need to send a string version
                stringtemperature = '{:.2f}'.format(temperature)
                # set this new value into the vector
                vector['temperature'] = stringtemperature
                # and transmit it to the client
                await vector.send_setVector(timestamp=timestamp)
                # Notify the queue that the work has been processed.
                txque.task_done()


    def make_driver():
        "Returns an instance of the driver"

        # create a queue to transmit from thermalcontrol
        txque = asyncio.Queue(maxsize=5)

        thermalcontrol = ThermalControl(txque)

        # create a vector with one number 'temperaturemember' as its member

        # Note: numbers must be given as strings
        stringtemperature = '{:.2f}'.format(thermalcontrol.temperature)
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

        # create a vector with one number 'targetmember' as its member
        stringtarget = '{:.2f}'.format(thermalcontrol.target)
        targetmember = NumberMember( name="target",
                                     format='%3.1f', min='-50', max='99',
                                     membervalue=stringtarget )
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

        # set the coroutine to be run with the driver
        pollingtask = thermalcontrol.poll_thermostat()

        # Create the Driver, containing this device and
        # other objects needed to run the instrument
        driver = ThermoDriver( devices=[thermostat],
                               tasks=[pollingtask],
                               txque=txque,
                               thermalcontrol=thermalcontrol )

        # and return the driver
        return driver


    if __name__ == "__main__":

        driver = make_driver()

        # In this example, set the driver to listen on a host/port
        server = IPyServer([driver], host="localhost",
                                     port=7624,
                                     maxconnections=5)

        asyncio.run(server.asyncrun())


Or alternatively, if you want the driver to communicate by stdin and stdout::


    if __name__ == "__main__":

        driver = make_driver()

        asyncio.run(driver.asyncrun())

        # Call this script, and when running copy and paste the
        # following xml into the terminal:

        # <getProperties version="1.7" />

        # To set a new target temperature, paste the following:

        # <newNumberVector device="Thermostat" name="targetvector"><oneNumber name="target">40</oneNumber></newNumberVector>

        # this simulates a client setting a target temperature of 40 degrees.
        # Every ten seconds you should see xml from the driver showing the
        # temperature changing towards the target.
