Summary
=======

The following summarises how a driver could be structured, describing a simulated LED control and button.

Your Class
^^^^^^^^^^

You would normally start by creating one or more classes or functions that control your hardware, for example::

    import asyncio

    from indipydriver import (IPyDriver, Device,
                              getProperties,
                              SwitchVector, SwitchMember, newSwitchVector,
                              IPyServer
                             )

    # Other vectors, members and events are available,
    # this example only imports those used.

    class LEDSwitchControl:
        """This is a simulation containing variables only, normally it
           would control a real LED on an output GPIO, and monitor a
           button on an input GPIO."""

        def __init__(self):
            "Set start up values"
            self._LED = False
            self._BUTTON = False

        def set_LED(self, value):
            "Set LED On or Off"
            self._LED = True if value == "On" else False

        def get_LED(self):
            "Return state, On or Off"
            if self._LED:
                return "On"
            else:
                return "Off"

        def get_BUTTON(self):
            "Return button, On or Off"
            if self._BUTTON:
                return "On"
            else:
                return "Off"

        async def buttoncycle(self):
            "Simulates the button being toggled every five seconds"
            while True:
                await asyncio.sleep(5)
                self._BUTTON = False if self._BUTTON else True



Subclass IPyDriver
^^^^^^^^^^^^^^^^^^

The IPyDriver class has signature::

    class ipydriver.IPyDriver(devices, **driverdata)

Where 'devices' is a list of devices this driver will control, each device being an instance of the 'Device' class. In this example a single device will be created with devicename set to "ledswitch".

The device object can contain multiple property vectors. In this example it will contain two vectors, one to hold the LED status, and one to hold the button status. A vector can hold multiple members, for example a radio button may hold a number of switches, in this example, each vector will only have one member.

The keyworded variable-length argument 'driverdata' contains any data you wish to set into the class, in this example it will consist of keyword 'control' set to an instance of your LEDSwitchControl class which will then be available as the attribute self.driverdata['control']

The class IPyDriver should be subclassed with your own 'clientevent(event)' and 'hardware()' coroutine methods::

    class LEDSwitchDriver(IPyDriver):

        async def clientevent(self, event):
            "On receiving data, this is called, and should handle any necessary actions"
            control =  self.driverdata["control"]
            match event:
                case getProperties():
                    await event.vector.send_defVector()

                case newSwitchVector(devicename="ledswitch",
                                     vectorname="ledvector") if "ledmember" in event:
                    received_value = event["ledmember"]
                    control.set_LED(received_value)
                    ledvector = event.vector
                    # On sending data, clients set their vector state to "Busy",
                    # so sending 'Ok' resets the state on the client
                    ledvector.state = 'Ok'
                    # set the ledmember to the current LED state
                    ledvector["ledmember"] = control.get_LED()
                    # and send the updated vector to the client
                    await ledvector.send_setVector()


        async def hardware(self):
            "This should be a continuously running coroutine"
            control =  self.driverdata["control"]
            # control is the instance of LEDSwitchControl
            cyclebutton = asyncio.create_task(control.buttoncycle())
            # the buttoncycle method is now running continuously
            # and simulates someone toggling the button

            # poll the hardware for any changes, and send changes to the client
            ledvector = self["ledswitch"]["ledvector"]
            buttonvector = self["ledswitch"]["buttonvector"]

            while True:
                await asyncio.sleep(0.1)
                # poll the device every 0.1 of a second,
                # send an update if values have changed
                ledvector.state = 'Ok'
                ledvector["ledmember"] = control.get_LED()
                await ledvector.send_setVector(allvalues=False)
                buttonvector.state = 'Ok'
                buttonvector["buttonmember"] = control.get_BUTTON()
                await buttonvector.send_setVector(allvalues=False)


clientevent method
^^^^^^^^^^^^^^^^^^

The event object is triggered by data received from the client, and is one of "enableBLOB", "getProperties", "newSwitchVector", "newNumberVector", "newTextVector" or "newBLOBVector".

The enableBLOB event can be ignored - it is used internally by IpyServer.

The getProperties event is sent by the client to discover the properties of the driver, and the reply you should generally use is shown above. The event has a 'vector' attribute, which is the vector being requested, and its send_defVector() method will transmit its definition back to the client.

The new vector events are sent by the client to change the instrument settings, in this case to switch on or off the LED. These events are mappings of membername to value which the client is submitting, not all membernames may be present if they are not being changed.

In this case the only event to be received will be a newSwitchVector for the devicename "ledswitch", and vectorname "ledvector" - as this is the only device and vector defined which can be controlled by the client, The buttonvector is read-only. If any other device or vector event is received, it can be ignored.

The client is setting the member's value, 'On' or 'Off' which is obtained from event["ledmember"]. In this example 'control' is an instance of your LEDSwitchControl class, which is actually your hardware that does the change, and so::

        received_value = event["ledmember"]
        control.set_LED(received_value)

Gets the value from the event, and sets it into LEDSwitchControl which sets the LED.

Having set the LED, you should set the vector state to ok, set its member "ledmember" to the LED value, and await the vector's send_setVector() method, which sends it to the client, confirming that the LED has changed state.

This covers receiving and replying to instructions, but you will also want to send instrument data to the client, for example if someone presses the button (which is simulated above by toggling the button every 5 seconds).  To handle this, you should create your own hardware() coroutine method.

hardware method
^^^^^^^^^^^^^^^

This coroutine is automatically started and should run continuously, typically with a 'while True' loop as shown above. You should take care not to call any long lived blocking function, which would disable the entire driver.

If your hardware control class (the LEDSwitchControl class above), needs any coroutines to be running, this is a good place to start them, as shown by the asyncio.create_task() line in the example.

The driver is a mapping to its devices, so self["ledswitch"] will get the device with devicename "ledswitch", and a device is a mapping to its vectors, so self["ledswitch"]["ledvector"] will return the vector controlling the LED and self["ledswitch"]["buttonvector"] will return the vector controlling the button.

A vector is a mapping to its member values, so::

    ledvector["ledmember"] = control.get_LED()

Sets the vector member with name "ledmember" to the value of the LED.

This vector, with updated member value can then be sent to the client using the vector's send_setVector() coroutine method.

The allvalues=False argument to send_setVector requests the method to not send all values, just those which have changed. So this will not be continuously sending updates if the LED has not changed state.

The same thing is done for the buttonvector, and the result is the vectors and their member values are sent to the client which displays the instrument status.


Make the driver
^^^^^^^^^^^^^^^

The driver, device, vectors etc,. have to be instantiated, it is suggested this is done in a make_driver() function::

    def make_driver():
        "Creates the driver"

        # create hardware object
        ledswitchcontrol = LEDSwitchControl()

        # create an led switch member
        ledmember = SwitchMember(name="ledmember",
                                 label="LED Control",
                                 membervalue=ledswitchcontrol.get_LED())

        # create a vector, in this case containing the single switch member.
        ledvector = SwitchVector(name="ledvector",
                                 label="LED Control",
                                 group="Control",
                                 perm="rw",
                                 rule = "AtMostOne",
                                 state="Ok",
                                 switchmembers=[ledmember] )

        # create a button member
        buttonmember = SwitchMember(name="buttonmember",
                                    label="Button Status",
                                    membervalue=ledswitchcontrol.get_BUTTON())

        # create a vector for the button.
        buttonvector = SwitchVector(name="buttonvector",
                                    label="Button status",
                                    group="Control",
                                    perm="ro",
                                    rule = "AtMostOne",
                                    state="Ok",
                                    switchmembers=[buttonmember] )

        # create a Device, containing the vectors
        ledswitch = Device( devicename="ledswitch", properties=[ledvector, buttonvector] )

        # Create the LEDSwitchDriver, in this case containing a single device,
        # together with your hardware object
        ledswitchdriver = LEDSwitchDriver(devices=[ledswitch], control=ledswitchcontrol)

        # and return the driver
        return ledswitchdriver

The various vector and member classes and their arguments are detailed further in this documentation.

Run the driver
^^^^^^^^^^^^^^

To run the driver include::

    if __name__ == "__main__":

        driver = make_driver()
        asyncio.run(driver.asyncrun())

In this case the driver will communicate on stdin and stdout if executed.

Alternatively::

    if __name__ == "__main__":

        driver = make_driver()
        server = IPyServer([driver], host="localhost", port=7624, maxconnections=5)
        asyncio.run(server.asyncrun())

In this case, the driver is set to listen on a host/port rather than stdin and stdout. If the host, port and maxconnections are not specified in the IPyServer call, the values shown above are the defaults.

The IPyServer class takes a list of drivers, only one in this example, and serves them all on the host/port. It allows connections from multiple clients. The drivers must all be created from IPyDriver subclasses - this is not a general purpose server able to run third party INDI drivers created with other languages or tools.

The next few pages of this documentation list the classes describing property vectors and members, if you wish to skip to further examples, see :ref:`example1`.
