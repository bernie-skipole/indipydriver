Example2
========

This example simulates a driver which snoops on the thermostat of the first example, and if the temperature becomes too hot, it opens a window, and closes it when the temperature drops.

This could be achieved by adding a new device to the thermostat driver, in which case snooping would not be required, however to illustrate the full functionality, this example is a separate driver, connected to indiserver, and communicating on stdin aand stdout::


    #!/usr/bin/env python3

    # indiserver 'runs' executable drivers, so the above shebang, together with making this
    # script executable ensures the driver can be run.

    import asyncio

    from indipydriver import (IPyDriver, Device,
                              LightVector, LightMember,
                              getProperties, newLightVector
                             )


    # Other vectors, members and events are available, this example only imports those used.

    # In this example, rather than simulating the control with global variables and top
    # level functions, all the hardware control is put in a class.

    class WindowControl:

        def __init__(self):
            "Set start up values"
            self.window = "Closed"
            self.updated = False

        def close_window(self):
            # a real driver would set hardware control here"
            self.window = "Closed"

        def open_window(self):
            # a real driver would set hardware control here"
            self.window = "Open"


    class WindowDriver(IPyDriver):

        """IPyDriver is subclassed here"""

        async def clientevent(self, event):
            """On receiving data, this is called, and should handle any necessary actions"""
               """
            await asyncio.sleep(0)
            # note: using match - case is ideal for this situation,
            # but requires Python v3.10 or later
            match event:
                case getProperties():
                    event.vector.send_defVector()


        async def hardware(self):
            """Check that temperature is being received, if not, transmit a getProperties
               and also send an alarm to the client"""
            device = self['Window']
            while True:
                asyncio.sleep(60)
                await device.devicecontrol()
