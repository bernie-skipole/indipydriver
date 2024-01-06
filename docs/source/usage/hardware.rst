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
                await temperaturevector.send_setVector(timeout='10')

                temperature = control.temperature
                message = "No further data"

                # Now set the status lights.
                if temperature < 5.0:
                    message="Warning: Low Temperature"
                    statusvector["frost"] = "Alert"
                elif control.target < 5.0:
                    # frost is not emminent, but show Idle light as warning
                    # that the target is set too low, causing a risk of frost.
                    message="Warning: Low Target"
                    statusvector["frost"] = "Idle"
                else:
                    statusvector["frost"] = "Ok"
                if temperature > 30.0:
                    message="Warning: High Temperature"
                    statusvector["hot"] = "Alert"
                else:
                    statusvector["hot"] = "Ok"
                if control.heater == "On":
                    statusvector["heater"] = "Busy"
                else:
                    statusvector["heater"] = "Ok"
                # send this vector, but with allvalues=False so it
                # is only sent as the values change
                await statusvector.send_setVector(message=message, allvalues=False)


devhardware
^^^^^^^^^^^

If your driver contains several devices, it could be messy including the code to handle all the devices in the driver hardware method. You may find it simpler to delegate the hardware control to each device, separating the code to where it is most relevant.

The Device class has method::

    async def devhardware(self, *args, **kwargs):

You could subclass the Device class, and override this method to control the hardware of that particular device, in which case the driver hardware method would need to await each of the devices devhardware methods.

For example the driver hardware method would contain the line::

    await self[devicename].devhardware()

which awaits the device's devhardware method, containing the code to run that device. If you have multiple devices this could be done using the asyncio.gather function.

To help in doing this, the constructor for each device has keyword dictionary 'devicedata' set as an attribute of the device, so when you create an instance of the device you can include any hardware related object required.

The args and kwargs arguments of devhardware are there so you can pass in any argument you like when calling this method.


Events
^^^^^^

On receiving data from a client, an 'event' is created and the clientevent method is awaited. You should create this method to handle data sent by the client.

The 'event' is any one of enableBLOB, getProperties, newSwitchVector, newTextVector, newNumberVector or newBLOBVector objects, these 'newxxxVector' objects are requests from the client to update the members of a vector.

The enableBLOB event can be ignored - it is used internally by IpyServer. If a getProperties is received, you should typically respond with::

    await event.vector.send_defVector()

This sends a vector definition to the client.

These new vector events have attribute 'vector' which is the vector to be updated, and are also mappings of membername to new membervalue. Typically you would create code to test which vector is being altered, obtain the new member value (from event[membername]) and update your instrument accordingly.

You should then update the vector and call the vector's send_setVector() method to inform the client the update has been applied.

For example, in the case of receiving a target temperature for the thermostat, you could also set a warning when a target below 5.0 is set::

    async def clientevent(self, event):
        "On receiving data, this is called, and should handle any necessary actions"

        # The hardware control object is stored in the driverdata dictionary
        control = self.driverdata["control"]

        match event:
            case getProperties():
                await event.vector.send_defVector()

            case newNumberVector(devicename='Thermostat',
                                 vectorname='targetvector') if 'target' in event:
                newtarget = event['target']
                try:
                    target = self.indi_number_to_float(newtarget)
                except TypeError:
                    # ignore an incoming invalid number
                    pass
                else:
                    control.target = target
                    event.vector['target'] = control.stringtarget
                    # If the target is below 5C warn of the
                    # danger of frost due to the target being low
                    if target < 5.0:
                        event.vector.state = 'Alert'
                        await event.vector.send_setVector(message="Setting a target below 5C risks frost damage")
                    else:
                        event.vector.state = 'Ok'
                        await event.vector.send_setVector(message="Target Set")


So the target is set, but the client GUI displays a warning.
