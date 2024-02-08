Summary
=======

The following summarises how a driver could be structured, describing a simulated LED control.

Your Class
^^^^^^^^^^

You would normally start by creating one or more classes or functions that control your hardware, for example::

    import asyncio

    from indipydriver import (IPyDriver, Device,
                              SwitchVector, SwitchMember, newSwitchVector,
                              getProperties, IPyServer
                             )


    # Other vectors, members and events are available,
    # this example only imports those used.

    class LED:
        """This is a simulation containing a variable only,
           normally it would control a real LED."""

        def __init__(self, value):
            "Set initial value of led"
            self.value = value
            # value should be 'On' or 'Off'



Subclass IPyDriver
^^^^^^^^^^^^^^^^^^

The IPyDriver class has signature::

    class IPyDriver(devices, tasks=[], **driverdata)

Where 'devices' is a list of devices this driver will control, each device being an instance of the 'Device' class. In this example a single device will be created with devicename set to "ledswitch".

The argument 'tasks' is a list of co-routines that you may have created to operate your instruments (to poll instrument values perhaps), the co-routines set in this list will all be started when the driver is run. This example does not use this functionality so tasks remains an empty list. The tasks argument was introduced in version 1.1.0.

A note on terminology here - a driver object can contain one or more devices, a device consists of one or more property 'vectors', where each vector object contains one or more members. A vector can be a 'Switch' vector, which may for example hold a number of switches which could define a radio button. Similarly a 'Text' vector holds text members, a 'Light' vector holds light members, a Numbers vector holds numbers and a BLOB vector holds Binary Large Objects.

In this example the device object will contain a single switch vector, with a single switch member, to control the LED.

The keyword argument 'driverdata' contains any data you wish to set into the class, in this example it will consist of keyword 'led' set to an instance of your LED class which will then be available as the attribute self.driverdata['led']

The class IPyDriver should be subclassed with your own 'clientevent(event)' coroutine method::

    class LEDDriver(IPyDriver):

        """IPyDriver is subclassed here."""

        async def clientevent(self, event):
            "On receiving data from the client, this is called"

            led = self.driverdata["led"]
            # led is an instance of the LED class
            match event:

                # event.vector is the vector being requested or altered
                # event[membername] is the new value

                case getProperties():
                    # An event of type 'getProperties' is a client request
                    # to define a property. Send back a property definition
                    await event.vector.send_defVector()

                case newSwitchVector(devicename="ledswitch",
                                     vectorname="ledswitchvector") if 'ledswitchmember' in event:
                    # a new value has been received from the client
                    newvalue = event["ledswitchmember"]
                    # set received value into led, this controls the actual LED
                    led.value = newvalue
                    # and set this new value into the vector
                    event.vector["ledswitchmember"] = newvalue
                    # send the updated vector back to the client
                    await event.vector.send_setVector()



clientevent method
^^^^^^^^^^^^^^^^^^

The event object is triggered by data received from the client, and is one of "enableBLOB", "getProperties", "newSwitchVector", "newNumberVector", "newTextVector" or "newBLOBVector".

The enableBLOB event can be ignored - it is used internally by IpyServer.

The getProperties event is sent by the client to discover the properties of the driver, and the reply you should generally use is shown above. The event has a 'vector' attribute, which is the vector being requested, and its send_defVector() method will transmit its definition back to the client.

The new vector events are sent by the client to change the instrument settings, in this case to switch on or off the LED. These events are mappings of membername to value which the client is submitting, not all membernames may be present if they are not being changed.

In this case the only event to be received will be a newSwitchVector for the devicename "ledswitch", and vectorname "ledswitchvector" - as this is the only device and vector defined which can be controlled by the client. If any other device or vector event is received, it can be ignored.

The client is setting the member's value, 'On' or 'Off' which is obtained from event["ledswitchmember"]. In this example 'led' is an instance of your LED class, which is actually your hardware that does the change, and so::

    newvalue = event["ledswitchmember"]
    led.value = newvalue

Gets the value from the event, and sets it into led which sets the LED - or in this simulation, just an object attribute.

You should then set the vector's member "ledswitchmember" to the new value, and await the vector's send_setVector() method, which sends it to the client, confirming that the led has changed state.

A vector is a mapping to its member values, so::

    event.vector["ledswitchmember"] = newvalue

Sets the vector member with name "ledswitchmember" to the new value, and::

    await event.vector.send_setVector()

Sends this new value to the client.



hardware method
^^^^^^^^^^^^^^^

In the example above no hardware coroutine is needed, but there may be instruments that need to send data periodically. The hardware coroutine is automatically started and should run continuously, typically with a 'while True' loop. Examples are given further in this documentation.

The driver is a mapping to its devices, so self["ledswitch"] will get the device with devicename "ledswitch", and a device is a mapping to its vectors, so self["ledswitch"]["ledswitchvector"] will return the vector controlling the LED.

This vector, with updated member value can then be sent to the client using the vector's send_setVector() coroutine method at regular intervals.


Make the driver
^^^^^^^^^^^^^^^

The driver, device, vectors etc,. have to be instantiated, it is suggested this is done in a make_driver() function::

    def make_driver():
        "Creates the driver"

        # create an object to control the instrument
        led = LED('Off')

        # create switch member
        ledswitchmember = SwitchMember(name="ledswitchmember",
                                       label="LED Value",
                                       membervalue=led.value)
        # set this member into a vector
        ledswitchvector = SwitchVector(name="ledswitchvector",
                                       label="LED",
                                       group="Control Group",
                                       perm="rw",
                                       rule='AtMostOne',
                                       state="Ok",
                                       switchmembers=[ledswitchmember] )
        # create a Device with this vector
        ledswitch = Device( devicename="ledswitch", properties=[ledswitchvector] )

        # Create the Driver (inherited from IPyDriver) containing this device
        # and also containing the led object which will be available as
        # self.driverdata['led']
        driver = LEDDriver(devices=[ledswitch], led=led)

        # The self.driverdata arguments should contain all objects which have
        # been created to run the instrument, so when this function returns
        # a reference will be retained and the objects will not be
        # garbage collected.

        # and return the driver
        return driver


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
