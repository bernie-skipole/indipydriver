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

It should be noted that the example would need a statement "from indipydriver import LightVector, LightMember" added to the head of the module. All the property vectors, and event vectors decribed later are available in the indipydriver package.

This statusvector would be included in the 'Thermostat' device::

        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector,
                                         targetvector,
                                         statusvector] )


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
                 # get the latest temperature
                temperature = control.temperature

                # set it into the temperature vector
                temperaturevector['temperature'] = temperature
                temperaturevector.send_setVector(timeout=10)

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
                statusvector.send_setVector(allvalues=False)
