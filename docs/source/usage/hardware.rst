Hardware
========


The driver has method::

    async def hardware(self)

This  is started when the driver is run, and should be a long running co-routine, controlling whatever hardware is required, and calling appropriate vector methods to send data.

To expand on the thermostat example; the driver could contain a further 'lights' vector with several members::

        frost = LightMember(name="frost", label="Frost Warning")
        hot = LightMember(name="hot", label="Over heating Warning")
        heater = LightMember(name="heater", label="Heater")

        # set these members into a vector
        statusvector = LightVector( name="statusvector",
                                    label="Status",
                                    group="Values",
                                    state="Ok",
                                    lightmembers=[frost, hot, heater] )

It should be noted that the example would need a statement "from indipydriver import LightVector, LightMember" added to the head of the module.

This statusvector would be included in the 'Thermostat' device::

        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector,
                                         targetvector,
                                         statusvector] )

        # And the Driver will contain this device
        driver = ThermoDriver(devices=[thermostat],  control=thermalcontrol)


The constructor of the driver has keyword dictionary 'driverdata' set as an attribute of the driver, so when you create an instance of the driver you can include any hardware related objects required.  In this case, the keyword 'control' has been set to an instance of the ThermalControl class, and therefore methods and attributes which control the hardware are available.

Driver methods have access to the thermalcontrol object simply by using::


       control = self.driverdata["control"]


The control object has coroutine method poll_thermostat(). When the hardware method is called, it can create a task from this co-routine, which is therefore immediately set running, and can then happily run in the background.


The hardware method becomes::

        async def hardware(self):
            "Run the hardware"
            # run the thermostat polling task
            control = self.driverdata["control"]
            poll_task = asyncio.create_task(control.poll_thermostat())

            # report temperature and status every ten seconds
            device = self['Thermostat']
            temperaturevector = device['temperaturevector']
            statusvector = device['statusvector']
            while True:
                await asyncio.sleep(10)

                # set the string temperature into the temperature vector
                temperaturevector['temperature'] = control.stringtemperature
                await temperaturevector.send_setVector(timeout=10)

                temperature = control.temperature

                # Now set the status lights.
                if temperature < 5.0:
                    statusvector["frost"] = "Alert"
                elif control.target < 5.0:
                    # frost is not emminent, but show Idle light as warning
                    # that the target is set too low, causing a risk of frost.
                    statusvector["frost"] = "Idle"
                else:
                    statusvector["frost"] = "Ok"
                if temperature > 30.0:
                    statusvector["hot"] = "Alert"
                else:
                    statusvector["hot"] = "Ok"
                if control.heater == "On":
                    statusvector["heater"] = "Busy"
                else:
                    statusvector["heater"] = "Ok"
                # send this vector, but with allvalues=False so it
                # is only sent as the values change
                await statusvector.send_setVector(allvalues=False)


devhardware
^^^^^^^^^^^

If your driver contains several devices, you may find it simpler to delegate the hardware control to each device.

The Device class has method::

    async def devhardware(self, *args, **kwargs):

You could subclass the Device class, and override this method to control the hardware of that particular device, in which case the driver hardware method would need to call each of the devices devhardware methods. Typically this could be done using the asyncio.gather function.

To help in doing this, the constructor for each device has keyword dictionary 'devicedata' set as an attribute of the device, so when you create an instance of the device you can include any hardware related object required.

The args and kwargs arguments of devhardware are there so you can pass in any argument you like when calling this method.
