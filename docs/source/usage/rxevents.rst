.. _rxevents:

RxEvents
========


The driver has method::

    async def rxevent(self, event):

When a request is received from the client, an event is produced, and this method is called. You should use this to check the event and take the appropriate action.

Typically you would start with::

    async def rxevent(self, event):
        match event:
            case newXXXXXVector( ....


The client event objects are described below, you never need to create these objects - they are automatically created by the received data, however you should test the event matches an object, and act accordingly.

All event objects have attributes devicename, vectorname, vector, root

Where vector is the vector object, and root is the received xml parsed as an xml.etree.ElementTree element.

.. autoclass:: indipydriver.enableBLOB

The INDI specification describes enableBLOB when sent from a client::

    Command to control whether setBLOBs should be sent to this channel from a
    given Device. They can be turned off completely by setting Never (the default),
    allowed to be intermixed with other INDI commands by setting Also or made the
    only command by setting Only.

    This behavior is only to be implemented in intermediate INDI server processes;
    individual Device drivers shall disregard enableBLOB and send all elements at will.


Your driver would normally ignore the enableBLOB event as the IPyServer class obeys it for you, however it is still presented as your application may wish to know about it, to log it for example.

The following event objects indicate the client is trying to set new member values of a vector. These events are mappings of membername:value which the client is submitting, you would typically use the rxevent method to accept these new values and set them into your instrument. The event has dict methods available such as get() and iteration through keys(), values() and items().

If you accept the new values, you should also set the vector with the new value, and send the vector back to the client to update it with the new value. The vector which these values apply to is made conveniently available as the event.vector attribute.


.. autoclass:: indipydriver.newSwitchVector

.. autoclass:: indipydriver.newTextVector

.. autoclass:: indipydriver.newNumberVector

.. autoclass:: indipydriver.newBLOBVector


The event also has a self.timestamp attribute which is a datetime object, or None if unable to parse the timestamp given in the protocol. In the attempt to parse, fractional minutes or seconds may be lost, and if no received timestamp is given, a current utc time is used. If the exact received timestamp is required it can be obtained from event.root.get("timestamp") which will return either the string from the received xml, or None if not present.

Typically, if you accept a new member value, you would have code that controls your instrument, and you would then set the new value into the vector and transmit the update to the client::

    # Match the event type, with devicename and vectorname
    # so event.vector is the vector belonging to this device
    # and with this vectorname

    case newXXXXXVector(devicename='AAA',
                        vectorname='BBB') if 'membername' in event:

        newvalue = event['membername']

        # your code to act on this newvalue, followed by:

        event.vector['membername'] = newvalue
        await event.vector.send_setVector()

When the client transmits the change, it assumes a state of Busy, until it gets confirmation the state has changed. Calling vector.send_setVector() therefore informs the client of the new value and resets the state on the client display.

It may be that you expect to receive multiple member values in a vector, and want to act on them all, in which case you may do something like::

    case newXXXXXVector(devicename='AAA',
                        vectorname='BBB'):

        for name, value in event.items():
            # your code to act on these values
            # followed by:
            event.vector[name] = value
        await event.vector.send_setVector()


devrxevent
^^^^^^^^^^

If your driver contains several devices, you may find it simpler to delegate the event control to each device.

The Device class has method::

    async def devrxevent(self, event, *args, **kwargs)

If desired you could subclass Device, and overwrite this method to handle events pertaining to this device. You would then
ensure devrxevent(event) is called using something like the code below in the driver::

    async def rxevent(self, event):
        match event:

            case newNumberVector(devicename='Thermostat'):
                await self['Thermostat'].devrxevent(event)

The Thermostat device method devrxevent(event) then handles those events targeted at devicename Thermostat.
