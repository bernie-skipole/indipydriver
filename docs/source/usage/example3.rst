Example3
========

This example simulates a driver which snoops on the thermostat of the previous example, and if the temperature becomes too hot, it opens a window, and closes it when the temperature drops::


    import asyncio

    from datetime import datetime, timezone, timedelta

    from indipydriver import (IPyDriver, Device,
                              LightVector, LightMember,
                              TextVector, TextMember,
                              getProperties, setNumberVector
                             )


    # Other vectors, members and events are available, this example only imports those used.


    class WindowControl:
        "This is a simulation containing variables only"

        def __init__(self, rxque):
            "Set initial value of window"
            self.window = "Open"
            # window should be "Open" or 'Closed'
            self.rxque = rxque
            self.timestamp = datetime.now(tz=timezone.utc)-timedelta(seconds=120)
            # initial timestamp is set at two minutes ago, to flag received temperature
            # is not current. This will be updated as soon as a temperature is received

        async def set_window(self):
            """Gets new temperature from rxque, sets window accordingly"""
            while True:
                temperature = await self.rxque.get()

                if temperature > 21:
                    self.window = "Open"
                if temperature < 18:
                    self.window = "Closed"

                # create timestamp to flag this temperature
                # has been received
                self.timestamp = datetime.now(tz=timezone.utc)

                # Notify the queue that the work has been processed.
                self.rxque.task_done()


    class WindowDriver(IPyDriver):

        """IPyDriver is subclassed here"""

        async def clientevent(self, event):
            """On receiving data from the client, this is called,
               Only a 'getProperties' is expected."""
            match event:
                case getProperties():
                    await event.vector.send_defVector()

        async def hardware(self):
            "Update client with window status"

            # Send an initial getProperties to snoop on Thermostat
            # This is necessary to inform IPyServer that this driver
            # wants copies of data sent from the thermostat
            await self.send_getProperties(devicename="Thermostat",
                                          vectorname="temperaturevector")

            windowcontrol = self.driverdata["windowcontrol"]

            alarmvector = self['Window']["windowalarm"]
            statusvector = self['Window']['windowstatus']
            while True:
                # every ten seconds send an update on window position
                await asyncio.sleep(10)
                statusvector['status'] = windowcontrol.window
                # and transmit it to the client
                await statusvector.send_setVector(allvalues=False)
                # allvalues=False means that not all values will be sent, only
                # values that have changed, so this avoids unnecessary data
                # being transmitted

                # check if windowcontrol.timestamp is older than 60 seconds
                if windowcontrol.timestamp < datetime.now(tz=timezone.utc)-timedelta(seconds=60):
                    # So no temperature data has been received in the last minute, re-send a getProperties,
                    # in case the thermostat was disconnected, and has hopefully restarted
                    await self.send_getProperties( devicename="Thermostat",
                                                   vectorname="temperaturevector" )
                    # and send an alarm to the client
                    alarmvector["alarm"] = "Alert"
                    await alarmvector.send_setVector(state="Alert")
                else:
                    # temperatures are being received
                    alarmvector["alarm"] = "Ok"
                    await alarmvector.send_setVector(state="Ok")


        async def snoopevent(self, event):
            """Handle receipt of an event from the Thermostat."""
            rxque = self.driverdata["rxque"]
            match event:
                case setNumberVector(devicename="Thermostat",
                                     vectorname="temperaturevector") if "temperature" in event:
                    # A setNumberVector has been sent from the thermostat to the client
                    # and this driver has received a copy, and so can read the temperature
                    try:
                        temperature = self.indi_number_to_float(event["temperature"])
                    except TypeError:
                        # ignore an incoming invalid number
                        pass
                    else:
                        # this updates windowcontrol
                        # which opens or closes the widow
                        await rxque.put(temperature)


    def make_driver():
        "Creates the driver"

        # create a queue
        rxque = asyncio.Queue(maxsize=5)

        # create hardware object
        windowcontrol = WindowControl(rxque)

        # create Light member
        alarm = LightMember(name="alarm", label="Reading thermostat", membervalue="Idle")
        # set this member into a vector
        windowalarm =  LightVector( name="windowalarm",
                                    label="Thermostat Status",
                                    group="Values",
                                    state="Idle",
                                    lightmembers=[alarm] )

        status = TextMember(name="status", label="Window position", membervalue=windowcontrol.window)
        windowstatus = TextVector(  name="windowstatus",
                                    label="Window Status",
                                    group="Values",
                                    perm="ro",
                                    state="Ok",
                                    textmembers=[status] )

        # create a Device with these vectors
        window = Device( devicename="Window",
                         properties=[windowalarm, windowstatus] )

        # set the coroutine to be run with the driver
        set_window = windowcontrol.set_window()

        # Create the WindowDriver (inherited from IPyDriver) containing this device
        windowdriver = WindowDriver( devices=[window],
                                     tasks=[set_window],
                                     rxque=rxque,
                                     windowcontrol=windowcontrol )

        # and return the driver
        return windowdriver


Assuming this module is windowcontrol.py, and the thermostat example is thermostat.py, these would be run with::


    import asyncio
    from indipydriver import IPyServer
    import thermostat, windowcontrol

    driver1 = thermostat.make_driver()
    driver2 = windowcontrol.make_driver()

    server = IPyServer([driver1, driver2])
    asyncio.run(server.asyncrun())
