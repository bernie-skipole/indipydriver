ClientEvents
============


The driver has method::

    async def clientevent(self, event):

When a request is received from the client, an event is produced, and this method is called. You should create the contents of this method to check the event and take the appropriate action.

Typically you would start with::

    async def clientevent(self, event):
        await asyncio.sleep(0)
        match event:
            case getProperties():
                event.vector.send_defVector()
            case ...


As this is a co-routine, starting with "await asyncio.sleep(0)" gives other tasks a chance to run.

In all cases you will need to handle the "getProperties()" event - in which the client is requesting information.  All events have a 'vector' attribute - which is the vector object the event is targetted at, so normally, you would call the vector send_defVector() method to respond to the client with the vector definition.

The client event objects are described below, you never need to create these objects - they are automatically created by the received data, however you should test the event matches an object, and act accordingly.

All event objects have attributes devicename, vectorname, vector, root

Where vector is the vector object, and root is the received xml parsed as an xml.etree.ElementTree element.


.. autoclass:: indipydriver.getProperties

.. autoclass:: indipydriver.enableBLOB

The following event objects indicate the client is trying to set new member values of a vector. The event has an attribute self.timestamp, being a datetime.datetime object, and is also a mapping of membername:value which the client is submitting.

Typically, if you accept a new value, you would have code that controls your instrument, and you would then set the new value into the vector and transmit the update to the client::

    # Match the event type, with devicename and vectorname
    # so event.vector is the vector belonging to this device
    # and with this vectorname

    case newXXXXXVector(devicename='AAA', vectorname='BBB'):

        if 'membername' in event:
            newvalue = event['membername']

            # your code to act on this newvalue, followed by:

            event.vector['membername'] = newvalue
            event.vector.state = 'Ok'
            event.vector.send_setVector()

Setting the state to Ok is necessary, as when the client transmits the change, it assumes a state of Busy, until it gets confirmation the state has changed.

The new Vector events are:


.. autoclass:: indipydriver.newSwitchVector

.. autoclass:: indipydriver.newTextVector

.. autoclass:: indipydriver.newNumberVector

.. autoclass:: indipydriver.newBLOBVector


When handling an event, more than one 'send_setvector' can be sent, you are not limited to just the event.vector.

Expanding the thermostat example with the "statusvector" set of lights introduced in the last section. When a target temperature is received, if the target is below 5.0, then the frost light should give some warning, and the response could be::

    case newNumberVector(devicename='Thermostat', vectorname='targetvector'):
        if 'target' in event:
            newtarget = event['target']
            TARGET = self.indi_number_to_float(newtarget)
            event.vector['target'] = TARGET
            event.vector.state = 'Ok'
            event.vector.send_setVector()
            # If the target is below 5C, warn of the danger of frost
            statusvector = self['Thermostat']['statusvector']
            if TARGET < 5.0:
                statusvector["frost"] = 'Idle'
                statusvector.send_setVector()
                self['Thermostat'].send_device_message(message="Setting a target below 5C risks frost damage")

So the target is set ok, but the client GUI displays a warning.
