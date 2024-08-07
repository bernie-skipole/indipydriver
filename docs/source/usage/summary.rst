Summary
=======

The following summarises how a driver could be structured, describing an LED control on a Raspberry Pi.

Subclass IPyDriver
^^^^^^^^^^^^^^^^^^

The IPyDriver class has signature::

    class IPyDriver(*devices, **driverdata)

Where 'devices' is one or more devices this driver will control, each device being an instance of the 'Device' class. In this example a single device will be created with devicename set to "led".

Keyword arguments set into 'driverdata' could contain any optional data you wish to set into the class, and which will then be available to your rxevent and hardware methods. In general this can be used to pass in your object which does the actual instrument control. In this example this feature is used to pass in a gpiozero.LED object.

A note on terminology here - a driver object can contain one or more devices, a device consists of one or more property 'vectors', where each vector object contains one or more members. A vector can be a 'Switch' vector, which may for example hold a number of switches which could define a radio button. Similarly a 'Text' vector holds text members, a 'Light' vector holds light members, a Numbers vector holds numbers and a BLOB vector holds Binary Large Objects.

In this example the device object will contain a single switch vector, with a single switch member, to control the LED.

The class IPyDriver should be subclassed with your own 'rxevent(event)' coroutine method::

    import asyncio
    import indipydriver as ipd

    from gpiozero import LED


    class LEDDriver(ipd.IPyDriver):

        """IPyDriver is subclassed here to create an LED driver."""

        async def rxevent(self, event):
            "On receiving data from the client, this is called"

            # get the object controlling the instrument, which is available
            # in the class named arguments dictionary 'self.driverdata'.
            led = self.driverdata["led"]

            match event:

                # event.vector is the vector being requested or altered
                # event[membername] is the new value

                case ipd.getProperties():
                    # An event of type 'getProperties' is a client request
                    # to define a property. Send back a property definition
                    await event.vector.send_defVector()

                case ipd.newSwitchVector(devicename="led",
                                         vectorname="ledvector") if 'ledmember' in event:
                    # a new value has been received from the client
                    ledvalue = event["ledmember"]
                    # turn on or off the led
                    if ledvalue == "On":
                        led.on()
                    elif ledvalue == "Off":
                        led.off()
                    else:
                        # not valid
                        return
                    # and set this new value into the vector
                    event.vector["ledmember"] = ledvalue
                    # send the updated vector back to the client
                    await event.vector.send_setVector()



rxevent method
^^^^^^^^^^^^^^

The event object is triggered by data received from the client, and is one of "enableBLOB", "getProperties", "newSwitchVector", "newNumberVector", "newTextVector" or "newBLOBVector".

The enableBLOB event can be ignored - it is used internally by IPyServer.

The getProperties event is sent by the client to discover the properties of the driver, and the reply you should generally use is shown above. The event has a 'vector' attribute, which is the vector being requested, and its send_defVector() method will transmit its definition back to the client.

The new vector events are sent by the client to change the instrument settings, in this case to switch on or off the LED. These events are mappings of membername to value which the client is submitting, not all membernames may be present if they are not being changed.

In this case the only event to be received will be a newSwitchVector for the devicename "led", and vectorname "ledvector" - as this is the only device and vector defined which can be controlled by the client. If any other device or vector event is received, it can be ignored.

The client is setting the member's value, 'On' or 'Off' which is obtained from event["ledmember"]. In this example the gpiozero 'LED' object is set accordingly.::

    ledvalue = event["ledmember"]

Gets the value from the event, and is then used to set the LED.

You should then set the vector's member "ledmember" to the new value, and await the vector's send_setVector() method, which sends it to the client, confirming that the led has changed state.

A vector is a mapping to its member values, so::

    event.vector["ledmember"] = ledvalue

Sets the vector member with name "ledmember" to the new value, and::

    await event.vector.send_setVector()

Sends this new value to the client.


hardware method
^^^^^^^^^^^^^^^

In the example above no hardware coroutine is needed, but there may be instruments that need to send data periodically. The hardware coroutine is automatically started and normally runs continuously, typically with a 'while not self.stop' loop. (self.stop is an attribute set to True if shutdown() is called on a driver). Examples are given further in this documentation.

The driver is a mapping to its devices, so self["led"] will get the device with devicename "led", and a device is a mapping to its vectors, so self["led"]["ledvector"] will return the vector controlling the LED.

This vector, with updated member value can then be sent to the client using the vector's send_setVector() coroutine method at regular intervals.


Make the driver
^^^^^^^^^^^^^^^

The driver, device, vectors etc,. have to be instantiated, it is suggested this is done in a make_driver() function::

    def make_driver(led):
        "Creates the driver, led is a gpiozero.LED object"

        # Note that “is_lit” is a property of the gpiozero LED
        # object and is True if the LED is on, this is used to
        # set up the initial value of ledmember.

        ledvalue = "On" if led.is_lit else "Off"

        # create switch member
        ledmember = ipd.SwitchMember(name="ledmember",
                                     label="LED Value",
                                     membervalue=ledvalue)
        # set this member into a vector
        ledvector = ipd.SwitchVector(name="ledvector",
                                     label="LED",
                                     group="Control Group",
                                     perm="rw",
                                     rule='AtMostOne',
                                     state="Ok",
                                     switchmembers=[ledmember] )
        # create a Device with this vector
        leddevice = ipd.Device( devicename="led", properties=[ledvector])

        # Create the Driver containing this device, and the actual
        # LED object used for instrument control as a named argument
        driver = LEDDriver(leddevice, led=led)

        # and return the driver
        return driver


The various vector and member classes and their arguments are detailed further in this documentation.

Run the driver
^^^^^^^^^^^^^^

To run the driver include::

    if __name__ == "__main__":

        # set up the LED pin and create and serve the driver
        led = LED(17)
        driver = make_driver(led)
        server = ipd.IPyServer(driver, host="localhost", port=7624, maxconnections=5)
        asyncio.run(server.asyncrun())

If the host, port and maxconnections are not specified in the IPyServer call, the values shown above are the defaults.

The IPyServer class takes drivers, only one in this example, and serves them all on the host/port. It allows connections from multiple clients. The drivers in the positional arguments must all be created from IPyDriver subclasses.

To run third party INDI drivers created with other languages or tools, the server object has an add_exdriver method, which given an executable will run it, and will communicate to it by stdin and stdout. The method can be called multiple times to add several executable drivers.

It also has an add_remote method which can be used to add connections to remote servers, creating a tree network of servers.

Connecting using the indipyclient terminal client gives:

.. image:: ./images/led.png


The next few pages of this documentation list the classes describing property vectors and members, if you wish to skip to further examples, see :ref:`example1`.
