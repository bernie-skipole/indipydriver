.. _example1:

Example1
========

The following example shows a simulated thermostat and heater which
maintains a temperature around 15C.

In this example a NumberVector and NumberMember
contains the temperature which is reported to the client::


    import asyncio

    from datetime import datetime, timezone

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

        # create a device with temperaturevector as its only property
        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector] )

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
        # rather than stdin and stdout.

        server = IPyServer([driver])
        asyncio.run(server.asyncrun())

        # To see this working, in another terminal try "telnet localhost 7624" and
        # Copy and paste the following xml into the terminal:

        # <getProperties version="1.7" />

        # You should see the vector definition xml returned followed by the
        # temperature being reported every ten seconds.


In summary. You create any objects or functions needed to operate your
hardware, and these can be inserted into the IPyDriver constructor.

You should note that in the above example an asyncio.Queue was used to pass data
from the thermometer to the driver. The Queue maxsize was arbitrarily set at five,
since if the communications link to client was having trouble, then it would not
be wise to allow an increasingly large number of points to be stored in the queue.

You would typically create your own child class of IPyDriver, overriding methods:

async def clientevent(self, event) - to handle incoming calls from the client.

async def hardware(self) - to run any continuous tasks.

You would also create members which contain values to be sent or received from
the client, one or more members are included in vectors.

The driver can manage multiple devices.

Each device contains one or more vectors.

Eech vector contains one or more members.

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
