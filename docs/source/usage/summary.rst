Summary
=======

The following summarises how a driver could be structured, describing a simulated LED On or Off switch.

Your Class
^^^^^^^^^^

You would normally start by creating one or more classes or functions that control your hardware, for example::

    import asyncio

    from indipydriver import (IPyDriver, Device,
                              getProperties,
                              SwitchVector, SwitchMember, newSwitchVector
                             )

    # Other vectors, members and events are available,
    # this example only imports those used.

    class LEDSwitch:
        """This is a simulation containing a variable only, normally it
           would control a real LED."""

        def __init__(self):
            "Set start up values"
            self._LED = False

        def set_LED(self, value):
            "Set LED On or Off"
            if value == "On":
                self._LED = True
            elif value == "Off":
                self._LED = False
            # any other value is ignored

        def get_LED(self):
            "Return state, On or Off"
            if self._LED:
                return "On"
            else:
                return "Off"

Subclass IPyDriver
^^^^^^^^^^^^^^^^^^

The class IPyDriver would then be subclassed, eventually an instance will be created, which will have access to an instance of your LEDSwitch class in its self.driverdata attribute. You should create your own clientevent(event) coroutine method::

    class LEDDriver(IPyDriver):

        async def clientevent(self, event):
            "On receiving data, this is called, and should handle any necessary actions"
            control =  self.driverdata["control"]
            match event:
                case getProperties():
                    await event.vector.send_defVector()

                case newSwitchVector(devicename="led", vectorname="ledswitchvector"):
                    received_value = event.get("ledswitchmember")
                    control.set_LED(received_value)
                    # sending 'Ok' informs the client that the value has been received
                    event.vector.state = 'Ok'
                    event.vector["ledswitchmember"] = control.get_LED()
                    await event.vector.send_setVector()

The event object is one of "getProperties", "enableBLOB", "newSwitchVector", "newNumberVector", "newTextVector" or "newBLOBVector".

The getProperties event is sent by the client to discover the properties of the driver, and the reply you should generally use is shown above. The event has a 'vector' attribute which is the vector being requested, and its send_defVector() method will transmit its definition back to the client.

The enableBLOB vector can be ignored - it is used by IpyServer.

In this case the only new vector to be received will be a newSwitchVector for the LED switch, and the event.vector attribute is the vector with name "ledswitchvector". This vector, and the device with devicename 'led' are created and added to the driver when it is instantiated, which will be described shortly.

Calling event.get("ledswitchmember") gets the member's value ('On' or 'Off'), or None if this member is not included in the received newSwitchVector. In this example 'control' is an instance of your LEDSwitch class, and so calling its set_LED method sets the LED.

Finally, having set the LED, you should set the vector state to ok, set its member "ledswitchmember" to the switch value, and await the vector's send_setVector() method, which sends it to the client, confirming that the switch has changed state.

This covers receiving instructions from the client, but you will also want to send instrument data to the client, for example if someone manually throws a switch and turns on/off the LED.  To handle this, you should create your own hardware() coroutine method::


        async def hardware(self):
            "This should be a continuously running coroutine"
            control =  self.driverdata["control"]
            vector = self["led"]["ledswitchvector"]
            while True:
                await asyncio.sleep(0.1)
                # poll the switch every 0.1 of a second, and if its value has changed
                # send an update
                oldvalue = vector["ledswitchmember"]
                actualvalue = control.get_LED()
                if oldvalue != actualvalue:
                    vector.state = 'Ok'
                    vector["ledswitchmember"] = actualvalue
                    await vector.send_setVector()

The driver is a mapping to its devices, so self["led"] will get the device with devicename "led", and a device is a mapping to its vectors, so self["led"]["ledswitchvector"] will return the vector with name "ledswitchvector", belonging to device with devicename "led", belonging to this driver.

This coroutine is started when the driver asyncrun() coroutine is started, and should run continuously, typically with a 'while True' method. You should take care not to call any long lived blocking function, which would disable the entire driver.

Make the driver
^^^^^^^^^^^^^^^

The driver, device, vectors etc,. have to be instantiated, it is suggested this is done in a make_driver() function::

    def make_driver():
        "Creates the driver"

        # create hardware object
        ledswitch = LEDSwitch()

        # create switch member
        switchmember = SwitchMember(name="ledswitchmember",
                                    label="LED Switch",
                                    membervalue=ledswitch.get_LED())

        # create switch vector, in this case containing a single switch member.
        switchvector = SwitchVector(  name="ledswitchvector",
                                      label="LED Control",
                                      group="Control",
                                      perm="rw",
                                      rule = "AtMostOne",
                                      state="Ok",
                                      switchmembers=[switchmember] )

        # create a Device, in this case containing a single vector
        leddevice = Device( devicename="led", properties=[switchvector] )

        # Create the LEDDriver, in this case containing a single device,
        # together with your hardware object
        leddriver = LEDDriver(devices=[leddevice], control=ledswitch)

        # and return the driver
        return leddriver

The various vectors, members and their arguments are detailed further in this documentation.

Run the driver
^^^^^^^^^^^^^^

As it stands the module could be imported and the make_driver() function would be made available. To run it include::

    if __name__ == "__main__":

        driver = make_driver()
        asyncio.run(driver.asyncrun())

If the appropriate shebang line is used, and the script made executable, the driver will communicate on stdin and stdout if executed.

Alternatively::

    if __name__ == "__main__":

        driver = make_driver()
        driver.listen()
        asyncio.run(driver.asyncrun())

In this example, the driver is set to listen on a host/port rather than stdin and stdout. If the host and port are not specified in this method call, defaults of 'localhost' and port 7624 are used.

This has a limitation that it accepts only a single connection, so is useful in the case where a single driver is connected to a single client.

Alternatively, and starting with a "from indipydriver import IPyServer"::

    if __name__ == "__main__":

        driver = make_driver()
        server = IPyServer([driver])
        asyncio.run(server.asyncrun())

The IPyServer class takes a list of drivers (only one in this example) and can connect to multiple clients. Again the defaults of 'localhost' and 7624 are used in this example. The drivers must all be created from IPyDriver subclasses - this is not a general purpose server able to run third party INDI drivers created with other languages or tools.
