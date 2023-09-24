Properties
==========

A property vector is an object containing one or more 'members'.  For example a NumberVector will contain one or more NumberMember objects, each containing a number value.

This section documents the property vectors created and set into the device, and also the associated members.

All these vectors have arguments name, label, group, perm, state except for LightVector which does not have permission (being a read only value).

**name** is the vector name, any unique name consistent with xml can be used (normal ascii characters), however if you are working with astronomical instruments, and want compatability with other drivers and clients, see the site:

https://indilib.org/develop/developer-manual/101-standard-properties.html

Which provides a convention for property and member names.

**label** is a string which can be used by the client, if not given it will be set equal to the name.

**group** is a further label used by the client, which can be used to group properties together. It can be left blank if not used.

**perm** is the permission - set to one of 'ro', 'wo', 'rw' - so 'ro' means the client can only read the vector values, not set them.

**state** is the state of the vector, and is an attribute which can be set before calling a send_setVector method to inform the client of the state of the property.

state can be set to one of 'Idle', 'Ok', 'Busy', 'Alert'.

As well as these arguments, each vector has attribute 'enable'.

**enable** is by default True, and is automatically set to False if the send_delProperty() method is called. When False no further data is sent by this property and any incoming values are ignored, until the enable attribute is set True again. Calling send_delProperty() therefore has the effect of removing the property from the client.

If in the initial state of the device, it is required that a particular property should be hidden, then when the vector is first created, set vector.enable = False, and the vector will be disabled until the enable attribute is set True, and the vector send_defVector() method called, which informs the client of the existence of this property.

Each vector is also a mapping, of membername:memberVALUE  - note, not member object, rather it is the value held by the member. In the LED switch example, the value of the vector member is set by

vector["ledswitchmember"] = control.get_LED()

Numeric values are set into vectors as strings, this is to explicitly control how numbers are formatted and sent in the protocol, the only exception is blobsize, where the number should be an integer.

Each member has a name and label, again label is a string which can be used by the client, if not given it will be set equal to the name.

When transmitting a vector, using the send_setVector or send_setVectorMembers methods, the method has a timestamp argument. The specification requires this to be a UTC value. You can either create a datetime.datetime object with timezone UTC, or leave the argument as None, in which case the method will automatically insert a UTC timestamp.

One possible way you may want to create your own timestamp is::

    from datetime import datetime, timezone

    timestamp = datetime.now(tz=timezone.utc)


Text
^^^^

A TextVector takes one or more TextMember objects.

.. autoclass:: indipydriver.TextMember

.. autoclass:: indipydriver.TextVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers


Lights
^^^^^^

A LightVector takes one or more LightMember objects.

.. autoclass:: indipydriver.LightMember

.. autoclass:: indipydriver.LightVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers


Switches
^^^^^^^^

A SwitchVector takes one or more SwitchMember objects.

.. autoclass:: indipydriver.SwitchMember

.. autoclass:: indipydriver.SwitchVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers


Numbers
^^^^^^^

A NumberVector takes one or more NumberMember objects.

.. autoclass:: indipydriver.NumberMember

.. autoclass:: indipydriver.NumberVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers


The number format also accepts an INDI style "m" to specify sexagesimal in the form "%<w>.<f>m".

From the INDI spec::

   <w> is the total field width
   <f> is the width of the fraction. valid values are:
            9 -> :mm:ss.ss
            8 -> :mm:ss.s
            6 -> :mm:ss
            5 -> :mm.m
            3 -> :mm

            For example:

            to produce "-123:45" use %7.3m

            to produce "  0:01:02" use %9.6m


BLOBs
^^^^^

A BLOBVector takes one or more BLOBMember objects.

.. autoclass:: indipydriver.BLOBMember

.. autoclass:: indipydriver.BLOBVector
   :members: send_delProperty, send_defVector, send_setVectorMembers, set_blobsize

Note that BLOBVectors do not have a send_setVector method, it is considered the more explicit send_setVectorMembers should always be used for BLOB's.
