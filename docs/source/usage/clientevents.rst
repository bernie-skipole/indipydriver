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

The INDI specification describes enableBLOB as : Command to control whether setBLOBs should be sent to this channel from a given Device. They can be turned off completely by setting Never (the default), allowed to be intermixed with other INDI commands by setting Also or made the only command by setting Only.

newVectors
^^^^^^^^^^

The following event objects indicate the client is trying to set new member values of a vector.

The event is a mapping of membername:value which the client is submitting.

It also has a self.timestamp attribute which is a datetime object, or None if unable to parse the timestamp given in the protocol. In the attempt to parse, fractional minutes or seconds may be lost, and if no received timestamp is given, datetime.utcnow() is used. If the exact received timestamp is required it can be obtained from event.root.get("timestamp") which will return either the string from the received xml, or None if not present.

Typically, if you accept a new member value, you would have code that controls your instrument, and you would then set the new value into the vector and transmit the update to the client::

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
            try:
                target = self.indi_number_to_float(newtarget)
            except TypeError:
                # ignore an incoming invalid number
                pass
            else:
                control.target = target
                event.vector['target'] = control.stringtarget
                event.vector.state = 'Ok'
                await event.vector.send_setVector()
                # If the target is below 5C, and if the temperature is still
                # above 5.0, warn of the danger of frost due to the target being low
                statusvector = self['Thermostat']['statusvector']
                if target < 5.0 and control.temperature > 5.0:
                    statusvector["frost"] = 'Idle'
                    await statusvector.send_setVector(allvalues=False)
                    await self['Thermostat'].send_device_message(message="Setting a target below 5C risks frost damage")


So the target is set ok, but the client GUI displays a warning.


devclientevent
^^^^^^^^^^^^^^

If your driver contains several devices, you may find it simpler to delegate the event control to each device.

The Device class has method::

    async def devclientevent(self, event, *args, **kwargs)

If desired you could subclass Device, and overwrite this method to handle events pertaining to this device. You would then
ensure devclientevent(event) is called using something like the code below in the driver::

    async def clientevent(self, event):
        await asyncio.sleep(0)
        match event:
            case getProperties():
                await event.vector.send_defVector()

            case newNumberVector(devicename='Thermostat'):
                await self['Thermostat'].devclientevent(event)

The Thermostat device method devclientevent(event) then handles those events targeted at devicename Thermostat.
