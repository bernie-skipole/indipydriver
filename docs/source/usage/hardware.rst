Hardware
========


The driver has method::

    async def hardware(self)

This  is started when the driver is run, and should be a long running co-routine. Typically you would create a number of co routines - each having
a while True loop, and running continuously controlling whatever hardware is required, and calling appropriate vector methods to send data.

This co-routine would contain an "await asyncio.gather(the co routines)", to run them in the eventloop.

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

The poll_thermostat co-routine could be edited as::

    async def poll_thermostat(device):
        "poll thermostat every second"
        temperaturevector = device['temperaturevector']
        statusvector = device['statusvector']
        while True:
            await asyncio.sleep(1)
            # the control function turns on and off the heater to keep
            # the temperature near to the target.
            control()
            temperaturevector["temperature"] = TEMPERATURE
            # the temperaturevector is set, but not sent, that is done
            # by the send_update co-routine every ten seconds
            # Now set the status lights.
            if TEMPERATURE < 5.0:
                statusvector["frost"] = "Alert"
            elif TARGET < 5.0:
                # frost is not emminent, but show Idle light as warning
                # that the target is set too low, causing a risk of frost.
                statusvector["frost"] = "Idle"
            else:
                statusvector["frost"] = "Ok"
            if TEMPERATURE > 30.0:
                statusvector["hot"] = "Alert"
            else:
                statusvector["hot"] = "Ok"
            if HEATER == "On":
                statusvector["heater"] = "Busy"
            else:
                statusvector["heater"] = "Ok"
            # send this vector, but with allvalues=False so it
            # is only sent as the values change
            statusvector.send_setVector(allvalues=False)

and as before, the hardware method is::

        async def hardware(self):
            """This coroutine controls and monitors the instrument, and if required
               sends updates to the client"""
            device = self['Thermostat']
            # and gather async co-routines which poll the hardware and
            # send updates to the client
            await asyncio.gather(  poll_thermostat(device),
                                   send_update(device)  )
