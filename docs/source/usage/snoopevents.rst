SnoopEvents
===========


The driver has method::

    async def snoopevent(self, event):

If this driver is 'snooping' on other drivers or devices, this method should be written to handle events created as data is received.

Your code should typically use match and case to determine the type of event, and read the event contents, and then take any appropriate action.

Snooping
^^^^^^^^

Snooping can occur on a network of INDI drivers, typically using the program 'indiserver' to connect multiple drivers to a client.  A driver can transmit a 'getProperties' command using driver method::

    send_getProperties(devicename=None, vectorname=None)

which requests indiserver to copy traffic from a remote device to this driver.

If vectorname is None, then all traffic from the specified device will be copied, if devicename is None as well, then traffic from all devices will be copied.

Snooping is typically used when an instrument should only take actions if another remote instrument has already taken a required prior action.  Snooping may also be useful as a method of logging traffic.

To snoop on a remote device, send the getProperties command, and handle the incoming traffic using the snoopevent method. The snoop event objects are described below, you never need to create these objects - they are automatically created by the received data, however you should test the event matches an object, and act accordingly.

The event type passed into the method reflects the command sent by the remote device.

Events
^^^^^^

All snoop events have attributes devicename, root and timestamp.

.. autoclass:: indipydriver.Message

.. autoclass:: indipydriver.delProperty


def Vector events also all have attributes vectorname, label, group, state and message. They are also a mapping of membername:value, which should contain all the vector member names, so for example event['membername'] would give the value of that member.

.. autoclass:: indipydriver.defSwitchVector

.. autoclass:: indipydriver.defTextVector

.. autoclass:: indipydriver.defNumberVector

.. autoclass:: indipydriver.defLightVector

.. autoclass:: indipydriver.defBLOBVector


set Vector events all have attributes vectorname, message and state (which could be None if not given due to no change of state). These events are also a mapping of membername:value, so for example event['membername'] would give the value of that member. However this object may not include members if they have not changed.


.. autoclass:: indipydriver.setSwitchVector

.. autoclass:: indipydriver.setTextVector

.. autoclass:: indipydriver.setNumberVector

.. autoclass:: indipydriver.setLightVector

.. autoclass:: indipydriver.setBLOBVector
