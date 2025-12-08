Example4
========

This example is similar to example 3, operating a thermostat. However in this case the driver delegates the operation to a subclass of a Device object.

It may seem an unecessary complication, however the method could be useful if the driver runs multiple devices, and it keeps the logic of each device separate.

A simple subclass of the driver is created, sending events to devices, and running the device devhardware methods.

The device is subclassed to handle these events, rather than the driver handling them::


    # Simulated thermostat with settable target.
    # This example illustrates delegation to a Device class

    import asyncio

    import indipydriver as ipd

    from indipyserver import IPyServer

    class ThermalControl:
        """This is a simulation containing variables only, normally it
           would control a real heater, and take temperature measurements
           from a sensor."""

        def __init__(self, devicename, target=15):
            """Set start up values"""
            # It is useful to give this controlling object the devicename
            # reference, so it can be identified throughout the code
            self.devicename = devicename
            self.target = target
            self.temperature = 20
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


    # Note the driver class name below is not specific to the thermostat
    # since this is general purpose

    class DelegateDriver(ipd.IPyDriver):

        """IPyDriver is subclassed here, with methods
           to delegate control to any included devices"""

        async def rxevent(self, event):
            """On receiving data, this is called, it sends any received events
               to the appropriate device"""

            if event.devicename in self:
               await self[event.devicename].devrxevent(event)


        async def hardware(self):
            """This coroutine starts when the driver starts, and starts any
               devices devhardware() tasks"""

            # Note no await - the background tasks will automatically be added to a taskgroup

            for device in self.values():
                self.add_background(device.devhardware())



    class ThermoDevice(ipd.Device):

        """Device is subclassed here, with a method
           to run the thermalcontrol.run_thermostat() method,
           accept a target temperature,
           and to transmit the temperature to the client"""


        async def devrxevent(self, event):
            "On receiving data, this is called by the drivers rxevent method"

            thermalcontrol = self.devicedata["thermalcontrol"]

            if isinstance(event, ipd.newNumberVector):
                if event.vectorname == "targetvector" and 'target' in event:
                    # Set the received value as the thermostat target

                    # The self.indi_number_to_float method converts the received string,
                    # which may be in a number of formats to a Python float value. This
                    # can then be set into thermalcontrol
                    try:
                        target = self.indi_number_to_float( event['target'] )
                    except TypeError:
                        # ignore an incoming invalid number
                        return
                    # set new target
                    thermalcontrol.target = target
                    # and set the new target value into the vector,
                    # then transmit the vector back to client.
                    event.vector['target'] = target
                    await event.vector.send_setVector()


        async def devhardware(self):
            """This coroutine is added as a background task by the driver's
               hardware method."""

            # get the ThermalControl object which actually runs the
            # instrument, and which is available in the named
            # arguments dictionary 'self.devicedata'.
            thermalcontrol = self.devicedata["thermalcontrol"]

            # set the thermalcontrol instrument running
            self.add_background(thermalcontrol.run_thermostat())

            vector = self['temperaturevector']
            while not self.stop:
                await asyncio.sleep(10)
                # Send the temperature every 10 seconds
                vector['temperature'] = thermalcontrol.temperature
                # and transmit it to the client
                await vector.send_setVector()


    def make_driver(devicename, target):
        "Returns an instance of the driver"

        # Make an instance of the object controlling the instrument
        thermalcontrol = ThermalControl(devicename, target)

        # Make a NumberMember holding the temperature value
        temperature = ipd.NumberMember( name="temperature",
                                        format='%3.1f',
                                        membervalue=thermalcontrol.temperature )
        # Make a NumberVector instance, containing the member.
        temperaturevector = ipd.NumberVector( name="temperaturevector",
                                              label="Temperature",
                                              group="Values",
                                              perm="ro",
                                              state="Ok",
                                              numbermembers=[temperature] )

        # create a NumberMember holding the target value
        target = ipd.NumberMember( name="target",
                                   format='%3.1f', min=-50, max=99,
                                   membervalue=thermalcontrol.target )
        targetvector = ipd.NumberVector( name="targetvector",
                                         label="Target",
                                         group="Values",
                                         perm="rw",
                                         state="Ok",
                                         numbermembers=[target] )

        # note the targetvector has permission rw so the client can set it

        # create an instance of your subclass device with the two vectors
        # and since we are delegating operation to the ThermoDevice,
        # include the thermalcontrol object which will appear in self.devicedata
        thermostat = ThermoDevice( devicename=devicename,
                                   properties=[temperaturevector, targetvector],
                                   thermalcontrol=thermalcontrol )

        # Create the Driver which will contain this Device, note
        # the driver only needs the device object
        driver = DelegateDriver( thermostat )

        # and return the driver
        return driver



    if __name__ == "__main__":

        # create and serve the driver
        # the devicename has to be unique in a network of devices,
        # so rather than statically setting it, the name and
        # initial target temperature could come from script arguments

        # in this case we'll set the devicename as "Thermostat",
        # and the target as 15

        # make a driver for the instrument
        thermodriver = make_driver("Thermostat", 15)
        # and a server, which serves this driver
        server = IPyServer(thermodriver)
        print(f"Running {__file__} with indipydriver version {ipd.version}")
        asyncio.run(server.asyncrun())


This pattern of delegation to a device may be used to break up a complex driver across several modules. So each device, with its vectors, members and its contolling code could be separated. 
