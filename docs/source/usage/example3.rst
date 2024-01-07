Example3
========

This example simulates a driver which snoops on the thermostat of the first example, and if the temperature becomes too hot, it opens a window, and closes it when the temperature drops. It also shows how a device can be subclassed, to delegate functions to the device objects::


    import asyncio

    from indipydriver import (IPyDriver, Device,
                              LightVector, LightMember,
                              TextVector, TextMember,
                              getProperties, setNumberVector
                             )


    # Other vectors, members and events are available, this example only imports those used.

    # In this example the hardware control is put in a class.

    class WindowControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set start up values"
            self.window = "Closed"
            self.updated = False

        def set_window(self, temperature):
            "a real driver would set hardware control here"
            self.updated = True
            if temperature > 30:
                self.window = "Open"
            if temperature < 25:
                self.window = "Closed"


    class WindowDriver(IPyDriver):

        """IPyDriver is subclassed here"""

        async def clientevent(self, event):
            """On receiving data from the client, this is called,
               Only a 'getProperties' is expected."""
            match event:
                case getProperties():
                    await event.vector.send_defVector()

        async def hardware(self):
            """Send an initial getProperties to snoop on Thermostat"""
            await self.send_getProperties(devicename="Thermostat",
                                          vectorname="temperaturevector")
            # delegate hardware control to the Window 'devhardware' method
            # note self['Window'] is the Window device object,
            await self['Window'].devhardware()

        async def snoopevent(self, event):
            """On receiving an event from the Thermostat, delegate the
               action to the Window device to handle it."""
            match event:
                case setNumberVector(devicename="Thermostat"):
                    await self['Window'].devsnoopevent(event)


    class WindowDevice(Device):

        """Device is subclassed here"""

        async def devhardware(self, *args, **kwargs):
            """Check that temperature is being received, if not, transmit a getProperties
               and also send an alarm to the client"""
            # Every minute, check an updated flag from the control object, which is stored
            # in dictionary attribute self.devicedata
            control =  self.devicedata["control"]
            alarmvector = self["windowalarm"]
            while True:
                # set control.updated to False, wait 60 seconds, and if updated is not
                # True, this indicates no updates are coming from the thermostat, so show an alarm
                control.updated = False
                await asyncio.sleep(60)
                if not control.updated:
                    # no data received in the last minute, re-send a getProperties,
                    # in case the thermostat was disconnected, and has hopefully restarted
                    await self.driver.send_getProperties(devicename="Thermostat",
                                                         vectorname="temperaturevector")
                    # and send an alarm to the client
                    alarmvector["alarm"] = "Alert"
                    await alarmvector.send_setVector()

        async def devsnoopevent(self, event, *args, **kwargs):
            """Open or close the window depending on temperature received from snooped device"""
            # control is the 'hardware' object which has methods to operate the window
            control =  self.devicedata["control"]
            alarmvector = self["windowalarm"]
            statusvector = self["windowstatus"]
            match event:
                case setNumberVector(devicename="Thermostat",
                                     vectorname="temperaturevector") if "temperature" in event:
                    # A setNumberVector has been sent from the thermostat to the client
                    # and this driver has received a copy, and so can read the temperature
                    try:
                        temperature = self.driver.indi_number_to_float(event["temperature"])
                    except TypeError:
                        # ignore an incoming invalid number
                        pass
                    else:
                        # this updates the control.updated attribute
                        # and opens or closes the widow
                        control.set_window(temperature)
                        # send window status light to the client to
                        # indicate temperature is being received
                        alarmvector["alarm"] = "Ok"
                        await alarmvector.send_setVector(allvalues=False)
                        # and send text of window position to the client
                        statusvector["status"] = control.window
                        await statusvector.send_setVector(allvalues=False)


    def make_driver():
        "Creates the driver"

        # create hardware object
        windowcontrol = WindowControl()

        # create Light member
        alarm = LightMember(name="alarm", label="Reading thermostat", membervalue="Idle")
        # set this member into a vector
        windowalarm =  LightVector( name="windowalarm",
                                    label="Thermostat Status",
                                    group="Values",
                                    state="Ok",
                                    lightmembers=[alarm] )

        status = TextMember(name="status", label="Window position", membervalue=windowcontrol.window)
        windowstatus = TextVector(  name="windowstatus",
                                    label="Window Status",
                                    group="Values",
                                    perm="ro",
                                    state="Ok",
                                    textmembers=[status] )

        # create a WindowDevice (inherited from Device) with these vectors
        # and also containing the windowcontrol, so it can call on its methods.
        window = WindowDevice( devicename="Window",
                               properties=[windowalarm, windowstatus],
                               control=windowcontrol)

        # the windowcontrol object is placed into dictionary window.devicedata with key 'control'

        # Create the WindowDriver (inherited from IPyDriver) containing this device
        windowdriver = WindowDriver(devices=[window])

        # and return the driver
        return windowdriver


    if __name__ == "__main__":

        driver = make_driver()
        asyncio.run(driver.asyncrun())


Assuming this module is windowcontrol.py, and the thermostat example is thermostat.py, these would be run with::


    import asyncio
    from indipydriver import IPyServer
    import thermostat, windowcontrol

    driver1 = thermostat.make_driver()
    driver2 = windowcontrol.make_driver()

    server = IPyServer([driver1, driver2])
    asyncio.run(server.asyncrun())
