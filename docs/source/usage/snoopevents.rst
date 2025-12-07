.. _snoopevents:

SnoopEvents
===========


The driver has method::

    async def snoopevent(self, event):

If this driver is 'snooping' on other drivers, this method should be written to handle events created as data is received.

Snooping is typically used when an instrument should only take actions if another remote instrument has already taken a required prior action.  Snooping may also be useful as a method of logging traffic.

Your code should read the event contents, and then take any appropriate action.

Snooping
^^^^^^^^

A driver can be set to snoop on another drivers device and vector traffic with the method::

    snoop(devicename, vectorname, timeout=30)

This will cause the driver to transmit a 'getProperties' request, which will instruct servers to copy traffic originating from the specified device/vector to this driver, as if it was a connected client. Since intermediate servers may get switched off and on and lose the copy instruction, if no traffic is received after the timeout value, then another getProperties will be sent.

It is also possible for a driver to await a send_getProperties command directly using coroutine method::

    send_getProperties(devicename=None, vectorname=None)

This has the same effect as the snoop command, however without the timeout facility, and this command could have devicename and vectorname set to None.

If vectorname is None, then all traffic from the specified device will be copied, if devicename is None as well, then traffic from all devices will be copied (apart from devices on this particular driver).

As this has no timeout function it is up to user code to provide a repeating send_getProperties call if it is deemed necessary.

Note: in this implementation, snooping will not occur between devices on the same driver. Your driver code is handling all its devices, so should be able to control all traffic needed between them. However snooping can occur between drivers connected to the same IPyServer, or across multiple IPyServers linked together by remote connections.

When the copied traffic is received by this driver, the snoopevent method will be awaited. The snoop event objects are described below, you never need to create these objects - they are automatically created by the received data, however you should overwrite the snoopevent method to test the event matches an object, and act accordingly.

The event type passed into the method reflects the command sent by the remote device.

For complex snooping requirements, you may also want to access the following driver attributes:

self.snoopall

Normally False, will be set to True if the user calls send_getProperties without devicename or vectorname, so this flags that all traffic from remote devices will be snooped.

self.snoopdevices

As default this is an empty set. This will become a set of of remote device names if the user calls send_getProperties with devicename but no vectorname. Indicating that all vectors from the chosen device will be snooped.

self.snoopvectors

As default this is an empty dictionary.

The keys of self.snoopvectors will become tuples (devicename,vectorname) of vectors that are being snooped.

The values will be either None or lists of [timeout, timestamp]

The None values are set as the remote vectors are learnt as devices are being snooped.

However if the snoop method has been called to snoop on a particular vector, the [timeout, timestamp] values will be created.

timeout is the integer seconds set by the snoop() method

timestamp is updated whenever snoop data from the vector is received.

A monitoring coroutine checks if current time is greater than timeout+timestamp, and if it is, sends a getproperties for that device and vector.

It would therefore be possible to call send_getProperties, and after a short while inspect the keys of self.snoopvectors to view a list of all remote devices and vectors on the network.


Events
^^^^^^

All snoop events have attributes devicename, root and timestamp. The root is an xml.etree.ElementTree object. The timestamp is a datetime object, or None if unable to parse the timestamp given in the protocol. In the attempt to parse, fractional minutes or seconds may be lost, and if no received timestamp is given, datetime.utcnow() is used. If the exact received timestamp is required it can be obtained from event.root.get("timestamp") which will return either the string from the received xml, or None if not present.

.. autoclass:: indipydriver.Message

.. autoclass:: indipydriver.delProperty


def Vector events also all have attributes vectorname, label, group, state and message. They are also a mapping of membername:value, which should contain all the vector member names, so for example event['membername'] would give the value of that member.

.. autoclass:: indipydriver.defSwitchVector

.. autoclass:: indipydriver.defTextVector

.. autoclass:: indipydriver.defNumberVector
   :members: getfloatvalue

.. autoclass:: indipydriver.defLightVector

.. autoclass:: indipydriver.defBLOBVector


set Vector events all have attributes vectorname, message and state (which could be None if not given due to no change of state). These events are also a mapping of membername:value, so for example event['membername'] would give the value of that member. However this object may not include members if they have not changed.


.. autoclass:: indipydriver.setSwitchVector

.. autoclass:: indipydriver.setTextVector

.. autoclass:: indipydriver.setNumberVector
   :members: getfloatvalue

.. autoclass:: indipydriver.setLightVector

.. autoclass:: indipydriver.setBLOBVector
