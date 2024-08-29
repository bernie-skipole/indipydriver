Example3
========

This example simulates a driver which snoops on the thermostat of the previous example, and if the temperature becomes too hot, it opens a window, and closes it when the temperature drops::


    import asyncio, time

    from indipydriver import (IPyServer, IPyDriver, Device,
                              TextVector, TextMember,
                              setNumberVector
                             )

    # Other vectors, members and events are available, this example only imports those used.

    class WindowControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set initial value of window"
            self.window = "Open"
            # window should be "Open" or 'Closed'


        def set_window(self, temperature):
            """Gets new temperature, sets window accordingly"""
            if temperature > 21:
                self.window = "Open"
            if temperature < 18:
                self.window = "Closed"


    class WindowDriver(IPyDriver):

        """IPyDriver is subclassed here"""

        async def hardware(self):
            "Update client with window status"

            windowcontrol = self.driverdata["windowcontrol"]
            statusvector = self['Window']['windowstatus']
            while not self.stop:
                # every ten seconds send an update on window position
                await asyncio.sleep(10)
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
                    windowcontrol.set_window(temperature)


    def make_driver(windowcontrol):
        "Creates the driver"

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
        windowdriver = WindowDriver( window,
                                     windowcontrol=windowcontrol )

        # This driver wants copies of data sent from the thermostat
        windowdriver.snoop(devicename="Thermostat",
                           vectorname="temperaturevector",
                           timeout=30)

        # and return the driver
        return windowdriver


    async def main(thermalcontrol, server):
        "Run the instrument and the server async tasks"
        await asyncio.gather(thermalcontrol.run_thermostat(),
                             server.asyncrun() )


    # Assuming the thermostat example is example2.py, these would be run with

    if __name__ == "__main__":

        import example2

        # Make the thermalcontrol object
        thermalcontrol = example2.ThermalControl()
        # make a driver
        thermodriver = example2.make_driver(thermalcontrol)

        # make the windowcontrol object
        windowcontrol = WindowControl()
        windowdriver = make_driver(windowcontrol)

        server = IPyServer(thermodriver, windowdriver)
        asyncio.run( main(thermalcontrol, server) )

Alternatively if the thermostat of example2 was running on a remote machine (with name 'raspberrypi'), then this script could be altered to remotely connect to it.

.. image:: ./images/rem3.png

Example2 would need one minor modification::

        server = IPyServer(thermodriver,
                           host="0.0.0.0",
                           port=7624,
                           maxconnections=5)

The server host has 'localhost' changed to "0.0.0.0" indicating it is listening on all IP addresses, allowing the window control machine to connect to it.

The machine operating the window could then be changed to::

    if __name__ == "__main__":

        # make the windowcontrol object
        windowcontrol = WindowControl()
        windowdriver = make_driver(windowcontrol)
        server = IPyServer(windowdriver)
        server.add_remote(host='raspberrypi', port=7624)
        asyncio.run(server.asyncrun())

The server.add_remote command enables this to make a connection to raspberrypi which is running the thermostat, and this connects the two. If indipyclient is then run on the machine running the windowdriver, it is able to control both drivers as before.
