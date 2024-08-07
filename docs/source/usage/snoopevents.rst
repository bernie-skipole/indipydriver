.. _snoopevents:

SnoopEvents
===========


The driver has method::

    async def snoopevent(self, event):

If this driver is 'snooping' on other drivers, this method should be written to handle events created as data is received.

Your code should typically use match and case to determine the type of event, and read the event contents, and then take any appropriate action.

Snooping
^^^^^^^^

Snooping can occur on a network of INDI drivers, typically connected together by IPyServer.  A driver can transmit a 'getProperties' command using driver coroutine method::

    send_getProperties(devicename=None, vectorname=None)

which requests the server utility to copy traffic from another driver/device to this driver.

If vectorname is None, then all traffic from the specified device will be copied, if devicename is None as well, then traffic from all devices will be copied (apart from devices on this particular driver).

Note: in this implementation, snooping will not occur between devices on the same driver. Your driver code is handling all its devices, so should be able to control all traffic needed between them. However snooping can occur between drivers connected to the same IPyServer, or across multiple IPyServers linked together by remote connections.

Snooping is typically used when an instrument should only take actions if another remote instrument has already taken a required prior action.  Snooping may also be useful as a method of logging traffic.

To snoop on a remote device, send the getProperties command, and handle the incoming traffic using the snoopevent method. The snoop event objects are described below, you never need to create these objects - they are automatically created by the received data, however you should test the event matches an object, and act accordingly.

The event type passed into the method reflects the command sent by the remote device.

Events
^^^^^^

All snoop events have attributes devicename, root and timestamp. The root is an xml.etree.ElementTree object. The timestamp is a datetime object, or None if unable to parse the timestamp given in the protocol. In the attempt to parse, fractional minutes or seconds may be lost, and if no received timestamp is given, datetime.utcnow() is used. If the exact received timestamp is required it can be obtained from event.root.get("timestamp") which will return either the string from the received xml, or None if not present.

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
