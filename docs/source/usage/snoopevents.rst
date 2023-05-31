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

which requests indiserver to copy traffic from a remote device and vector to this driver.

If vectorname is None, then all traffic from the specified device will be copied, if devicename is None as well, then traffic from all devices will be copied.

Snooping is typically used when an instrument should only take actions if another remote instrument has already taken a required prior action.  Snooping may also be useful as a method of logging traffic.

Therefore to snoop on a remote device, send the getProperties command, and handle the incoming traffic using the snoopevent method.

The event type passed into the method reflects the command sent by the remote device.

Events
^^^^^^

All snoop events have attributes devicename, root and timestamp.

.. autoclass:: indipydriver.Message

.. autoclass:: indipydriver.delProperty


def Vector events are also a mapping of membername:value.

.. autoclass:: indipydriver.defSwitchVector

.. autoclass:: indipydriver.defTextVector

.. autoclass:: indipydriver.defNumberVector

.. autoclass:: indipydriver.defLightVector

.. autoclass:: indipydriver.defBLOBVector


set Vector events are also a mapping of membername:value.


.. autoclass:: indipydriver.setSwitchVector

.. autoclass:: indipydriver.setTextVector

.. autoclass:: indipydriver.setNumberVector

.. autoclass:: indipydriver.setLightVector

.. autoclass:: indipydriver.setBLOBVector
