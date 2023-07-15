Example4
========

This example builds on the last, but adds a switch to either leave the window on Auto (temperature controlled) or sets the window to open or closed.

This consists of three switches in a vector - with a OneOfMany rule, so only one switch can be active::


    import asyncio

    from indipydriver import (IPyDriver, Device,
                              LightVector, LightMember,
                              TextVector, TextMember,
                              SwitchVector, SwitchMember, newSwitchVector,
                              getProperties, setNumberVector
                             )

    # Note that further Switch.... items have been imported.


    class WindowControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set start up values"
            self.window = "Closed"
            self.updated = False
            self.auto = True

        def set_window(self, temperature):
            "a real driver would set hardware control here"
            self.updated = True
            if self.auto:
                if temperature > 30:
                    self.window = "Open"
                if temperature < 25:
                    self.window = "Closed"

        @property
        def switch_auto(self):
            "Return switch status"
            if self.auto:
                return "On"
            else:
                return "Off"

        @property
        def switch_open(self):
            "Return switch status"
            if self.auto:
                return "Off"
            if self.window == "Open":
                return "On"
            return "Off"

        @property
        def switch_close(self):
            "Return switch status"
            if self.auto:
                return "Off"
            if self.window == "Closed":
                return "On"
            return "Off"


    class WindowDriver(IPyDriver):

        """IPyDriver is subclassed here"""

        async def clientevent(self, event):
            """On receiving data from the client, this is called,
               If a newSwitchVector is received, delegate the
               action to the Window device to handle it.."""
            match event:
                case getProperties():
                    await event.vector.send_defVector()
                case newSwitchVector(devicename="Window"):
                    await self['Window'].devclientevent(event)

        async def hardware(self):
            """Send an initial getProperties to snoop on Thermostat"""
            await self.send_getProperties(devicename="Thermostat",
                                          vectorname="temperaturevector")
            # delegate hardware control to the Window 'devhardware' method
            await self['Window'].devhardware()

        async def snoopevent(self, event):
            """On receiving an event from the Thermostat, delegate the
               action to the Window device to handle it."""
            match event:
                case setNumberVector(devicename="Thermostat"):
                    await self['Window'].devsnoopevent(event)


    class WindowDevice(Device):

        """Device is subclassed here"""

        async def devclientevent(self, event, *args, **kwargs):
            """Accept newSwitchVector to set window controls
               to either auto, open or close"""
            control =  self.devicedata["control"]
            statusvector = self["windowstatus"]
            match event:
                case newSwitchVector(devicename="Window", vectorname="windowswitches"):

                    if "auto" in event:
                        if event["auto"] == "On":
                            control.auto = True
                        elif event["auto"] == "Off":
                            control.auto = False
                    if not control.auto:
                        # not on auto, so act on open or close commands
                        if "open" in event:
                            if event["open"] == "On":
                                control.window = "Open"
                            elif event["open"] == "Off":
                                control.window = "Closed"
                        if "close" in event:
                            if event["close"] == "Off":
                                control.window = "Open"
                            elif event["close"] == "On":
                                control.window = "Closed"

                    # set any changes into the windowswitches vector members
                    event.vector["auto"] = control.switch_auto
                    event.vector["open"] = control.switch_open
                    event.vector["close"] = control.switch_close

                    # sending 'Ok' informs the client that the value has been received
                    event.vector.state = 'Ok'
                    await event.vector.send_setVector()

                    # and send text of window position to the client
                    statusvector["status"] = control.window
                    await statusvector.send_setVector(allvalues=False)



        async def devhardware(self, *args, **kwargs):
            """Check that temperature is being received, if not, transmit a getProperties
               and also send an alarm to the client"""
            # Every minute, check an updated flag from the control object
            control =  self.devicedata["control"]
            alarmvector = self["windowalarm"]
            while True:
                control.updated = False
                await asyncio.sleep(60)
                if not control.updated:
                    # no data received in the last minute, re-send a getProperties,
                    await self.driver.send_getProperties(devicename="Thermostat",
                                                         vectorname="temperaturevector")
                    # and send an alarm to the client
                    alarmvector["alarm"] = "Alert"
                    await alarmvector.send_setVector()


        async def devsnoopevent(self, event, *args, **kwargs):
            """Open or close the window depending on temperature received from snooped device"""
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
                        # open or close the widow, this only takes action
                        # if control.auto is True
                        control.set_window(temperature)
                        # send window status light to the client
                        alarmvector["alarm"] = "Ok"
                        await alarmvector.send_setVector(allvalues=False)
                        # and send text of window position to the client
                        statusvector["status"] = control.window
                        await statusvector.send_setVector(allvalues=False)


    def make_driver():
        "Creates the driver"

        # create hardware object
        windowcontrol = WindowControl()

        alarm = LightMember(name="alarm", label="Reading thermostat", membervalue="Idle")
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

        # create switch members and vector

        automember = SwitchMember(name="auto", label="Automatic", membervalue=windowcontrol.switch_auto)
        openmember = SwitchMember(name="open", label="Open", membervalue=windowcontrol.switch_open)
        closemember = SwitchMember(name="close", label="Close", membervalue=windowcontrol.switch_close)
        windowswitches = SwitchVector(  name="windowswitches",
                                        label="Window Control",
                                        group="Control",
                                        perm="rw",
                                        rule = "OneOfMany",
                                        state="Ok",
                                        switchmembers=[automember, openmember, closemember] )


        # create a WindowDevice (inherited from Device) with these vectors
        # and also containing the windowcontrol object, so it can call on its methods.
        window = WindowDevice( devicename="Window",
                               properties=[windowalarm, windowstatus, windowswitches],
                               control=windowcontrol )

        # the windowcontrol object is placed into dictionary window.devicedata with key 'control'

        # Create the WindowDriver (inherited from IPyDriver) containing this device
        windowdriver = WindowDriver(devices=[window])

        # and return the driver
        return windowdriver


    if __name__ == "__main__":

        driver = make_driver()
        asyncio.run(driver.asyncrun())
