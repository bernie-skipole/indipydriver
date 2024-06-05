Example3
========

This example simulates a driver which snoops on the thermostat of the previous example, and if the temperature becomes too hot, it opens a window, and closes it when the temperature drops::


    import asyncio, time

    from indipydriver import (IPyServer, IPyDriver, Device,
                              TextVector, TextMember,
                              getProperties, setNumberVector
                             )

    # Other vectors, members and events are available, this example only imports those used.

    class WindowControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set initial value of window"
            self.window = "Open"
            # window should be "Open" or 'Closed'
            self.update_time = time.time()
            # Set whenever a temperature update is requested

        def set_window(self, temperature):
            """Gets new temperature, sets window accordingly"""
            if temperature > 21:
                self.window = "Open"
            if temperature < 18:
                self.window = "Closed"
            # An update time is recorded to ensure the received
            # temperature is regularly obtained.
            self.update_time = time.time()


    class WindowDriver(IPyDriver):

        """IPyDriver is subclassed here"""

        async def rxevent(self, event):
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
            statusvector = self['Window']['windowstatus']
            while True:
                # every ten seconds send an update on window position
                await asyncio.sleep(10)
                now_time = time.time()
                if now_time - windowcontrol.update_time > 20.0:
                    # No new temperature has been received for longer than 20 seconds
                    # the thermostat could have been disconnected. Send another
                    # getProperties just in case it is reconnected
                    await self.send_getProperties(devicename="Thermostat",
                                                  vectorname="temperaturevector")
                    # It would also be possible to set an alarm
                    # to indicate the failure of received temperature

                # get the current window status
                statusvector['status'] = windowcontrol.window
                # and transmit it to the client
                await statusvector.send_setVector(allvalues=False)
                # allvalues=False means that not all values will be sent, only
                # values that have changed, so this avoids unnecessary data
                # being transmitted


        async def snoopevent(self, event):
            """Handle receipt of an event from the Thermostat."""
            windowcontrol = self.driverdata["windowcontrol"]
            match event:
                case setNumberVector(devicename="Thermostat",
                                     vectorname="temperaturevector") if "temperature" in event:
                    # A setNumberVector has been sent from the thermostat to the client
                    # and this driver has received a copy, and so can read the temperature
                    try:
                        temperature = self.indi_number_to_float(event["temperature"])
                    except TypeError:
                        # ignore an incoming invalid number
                        return
                    # this updates windowcontrol which opens or closes the widow
                    # and also updates its update_time
                    windowcontrol.set_window(temperature)


    def make_driver():
        "Creates the driver"

        # make the instrument controlling object
        windowcontrol = WindowControl()

        status = TextMember( name="status",
                             label="Window position",
                             membervalue=windowcontrol.window )
        windowstatus = TextVector( name="windowstatus",
                                   label="Window Status",
                                   group="Values",
                                   perm="ro",
                                   state="Ok",
                                   textmembers=[status] )

        # make a Device with this vector
        window = Device( devicename="Window",
                         properties=[windowstatus] )

        # Make the WindowDriver containing this Device
        # and the window controlling object
        windowdriver = WindowDriver( devices=[window],
                                     windowcontrol=windowcontrol )

        # and return the driver
        return windowdriver


    # Assuming the thermostat example is example2.py, these would be run with

    if __name__ == "__main__":

        import example2

        thermodriver = example2.make_driver()
        windowdriver = make_driver()

        server = IPyServer([thermodriver, windowdriver])
        asyncio.run(server.asyncrun())

Alternatively if example2 was running on a remote machine, then this script could be altered to remotely connect to it.  Example2 would need one minor modification::

    if __name__ == "__main__":
        driver = make_driver()
        server = IPyServer([driver], host="0.0.0.0",
                                     port=7624,
                                     maxconnections=5)
        asyncio.run(server.asyncrun())

The server host would have to be changed from 'localhost' to either the machines IP address, or to "0.0.0.0" indicating it is listenning on all IP addresses.

The machine operating the window would then need to be changed to::

    if __name__ == "__main__":
        windowdriver = make_driver()
        server = IPyServer([windowdriver])
        server.add_remote(host='raspberrypi', port=7624)
        asyncio.run(server.asyncrun())

Where the machine running the thermostat has name 'raspberrypi', and this connects the two. If indipyclient is then run on the machine running the windowdriver, it is able to control both drivers as before.

As a further variation, the thermostat of Example 2 on the Raspberry pi could have configuration::

    if __name__ == "__main__":
        driver = make_driver()
        driver.listen(host="0.0.0.0", port=7624)
        asyncio.run(driver.asyncrun())

This accepts the remote call from the machine running the window driver, but is a lighter option as it does not use IPyServer. Since it has no
