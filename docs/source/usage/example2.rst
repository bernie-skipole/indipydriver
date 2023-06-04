Example2
========

This example simulates a driver which snoops on the thermostat of the first example, and if the temperature becomes too hot, it opens a window, and closes it when the temperature drops.

This could be achieved by adding a new device to the thermostat driver, in which case snooping would not be required, however to illustrate the full functionality, this example is a separate driver, connected to indiserver, and communicating on stdin and stdout::


    #!/usr/bin/env python3

    # indiserver 'runs' executable drivers, so the above shebang, together with making this
    # script executable ensures the driver can be run.

    import asyncio

    from indipydriver import (IPyDriver, Device,
                              LightVector, LightMember,
                              TextVector, TextMember,
                              getProperties, setNumberVector
                             )


    # Other vectors, members and events are available, this example only imports those used.

    # In this example, rather than simulating the control with global variables and top
    # level functions, the hardware control is put in a class.

    class WindowControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set start up values"
            self.window = "Closed"
            self.updated = False

        def set_window(self, temperature):
            "a real driver would set hardware control here"
            if temperature > 30:
                self.window = "Open"
            if temperature < 25:
                self.window = "Closed"


    class WindowDriver(IPyDriver):

        """IPyDriver is subclassed here"""

        async def clientevent(self, event):
            """On receiving data from the client, this is called,
              Only a 'getProperties' is expected."""
            await asyncio.sleep(0)
            match event:
                case getProperties():
                    event.vector.send_defVector()

        async def hardware(self):
            """Start the Window device hardware by sending an initial
               getProperties to snoop on Thermostat, and then start
               the Window device hardware control"""
            self.send_getProperties(devicename="Thermostat")
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
            while True:
                control.updated = False
                asyncio.sleep(60)
                if not control.updated:
                    # no data received, re-send a getProperties, and send an alarm
                    self.driver.send_getProperties(devicename="Thermostat")
                    self["windowalarm"]["alarm"] = "Alert"
                    self["windowalarm"].send_setVector()

        async def devsnoopevent(self, event, *args, **kwargs):
            """Open or close the window depending on snooped device"""
            control =  self.devicedata["control"]
            match event:
                case setNumberVector(devicename="Thermostat", vectorname="temperaturevector"):
                    # received a temperature value from the thermostat
                    temperature = driver.indi_number_to_float(event["temperature"])
                    # flag a temperature value has been received
                    control.updated = True
                    # open or close the widow
                    control.set_window(temperature)
                    # send window status light to the client
                    self["windowalarm"]["alarm"] = "Ok"
                    self["windowalarm"].send_setVector()
                    # and send text of window position to the client
                    self["windowstatus"]["status"] = control.window
                    self["windowstatus"].send_setVector()


    def make_driver():
        "Creates the driver"

        # create hardware object
        windowcontrol = WindowControl()

        # create Light member
        alarm = LightMember(name="alarm", label="Reading thermostat")

        # set this member into a vector
        windowalarm =  LightVector( name="windowalarm",
                                    label="Thermostat Status",
                                    group="Values",
                                    state="Ok",
                                    lightmembers=[alarm] )

        status = TextMember(name="status", label="Window position")
        windowstatus = TextVector(  name="windowstatus",
                                    label="Window Status",
                                    group="Values",
                                    perm="ro",
                                    state="Ok",
                                    textmembers=[status] )



        # create a WindowDevice (inherited from Device) with these vectors
        # and also containing the windowcontrol, so it can call on its methods.
        window = WindowDevice( devicename="Window", properties=[windowalarm, windowstatus], control=windowcontrol)

        # the control object is placed into dictionary window.devicedata

        # Create the WindowDriver (inherited from IPyDriver) containing this device
        windowdriver = WindowDriver(devices=[window])

        # and return the driver
        return windowdriver


    if __name__ == "__main__":

        driver = make_driver()

        asyncio.run(driver.asyncrun())