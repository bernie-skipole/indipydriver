Property Vectors
================

A property vector is set with one or more 'members'.  For example a NumberVector will contain one or more NumberMember objects, each containing a number value.

The vector object is a mapping to a member value, so to access a value you could use vector['membername'], which for example, given a SwitchVector would be either "On" or "Off". Note, it is not a mapping to a member object, it is a mapping to the member value.

For example, to create a SwitchVector holding a set of three radio buttons:

s1 = SwitchMember("opt1", label="Option1, membervalue="On")

s2 = SwitchMember("opt2", label="Option2, membervalue="Off")

s3 = SwitchMember("opt3", label="Option3, membervalue="Off")

sv = SwitchVector("radio", label="Choose an option", group="Settings", perm="rw", rule="OneOfMany", state="Ok", switchmembers=[s1,s2,s3])

The rule "OneOfMany" ensures that this is a radio set, and only one button can be turned "On".

Once created sv["opt1"] will be "On".

As well as the methods documented below, vectors have dict methods such as get() and iteration through keys(), values() and items().

A number of attributes are common to all vectors.

Common Attributes
^^^^^^^^^^^^^^^^^

**name** is the vector name, any unique name consistent with xml can be used (normal ascii characters), however if you are working with astronomical instruments, and want compatability with other drivers and clients, see the site:

https://indilib.org/develop/developer-manual/101-standard-properties.html

Which provides a convention for property and member names.

**vectortype** Is equal to self.__class__.__name__ such as "SwitchVector" etc.,

**label** is a string which can be used by the client.

**group** is a further label used by the client, which can be used to group properties together. It can be left as an empty string if not used.

**perm** is the permission - set to one of 'ro', 'wo', 'rw' - so 'ro' means the client can only read the vector values, not set them. Not applicable for the LightVector which does not have permission (being a read only value).

**state** can be set to one of 'Idle', 'Ok', 'Busy' or 'Alert'. Typically the client displays this in an appropriate colour.

The state can be changed when calling a send_defVector, or send_setVector method where it is an optional argument of these methods. If the send method has argument state=None (the default), then the state attribute remains unchanged, however if the argument is set to one of the state values, then the state attribute is changed, and the client will receive the new state.

**timeout** indicates to the client the worst-case time it might take to change the value to something else.

The default of '0' implies that the vector will be updated in a minimal time should the client request it.

This attribute can be changed when calling a send_defVector, or send_setVector method where it is an optional argument of these methods. If the send method has timeout set to None (the argument default), then the timeout attribute remains unchanged, however if the argument is set to a numeric string, or to an integer or float - in which case it will be converted to string, then the timeout attribute is changed, and the client will receive the new timeout.

From the indi specification

"Each Property has a timeout value that specifies the worst-case time it might take to change the value to something else.
The Device may report changes to the timeout value depending on current device status. Timeout values give Clients a simple
ability to detect dysfunctional Devices or broken communication and also gives them a way to predict the duration of an
action for scheduling purposes..."


**enable** is by default True, and is automatically set to False if the send_delProperty() method is called. When False no further data is sent by this property and any incoming values are ignored, until the enable attribute is set True again. Calling send_delProperty() therefore has the effect of removing the property from the client.

If in the initial state of the device, it is required that a particular property should be hidden, then when the vector is first created, set vector.enable = False, and the vector will be disabled until the enable attribute is set True, and the vector send_defVector() method called, which informs the client of the existence of this property.

Each vector is also a mapping of membername to memberVALUE  - note, not member object, rather it is the value held by the member. In the LEDDriver example, the value of the vector member is set by::

    event.vector["ledmember"] = newvalue

Numeric values are preferably set into vectors as strings, this is to explicitly control how numbers are formatted and sent in the protocol. If given as floats or integers they will be converted to strings. The only exception is blobsize, where the number should be an integer.

When transmitting a vector, using the send_setVector or send_setVectorMembers methods, the method has a timestamp argument. The specification requires this to be a UTC value. You can either create a datetime.datetime object with timezone UTC, or leave the argument as None, in which case the method will automatically insert a UTC timestamp.

The Text, Light, Switch, Number and BLOB members and vectors are described below. When creating a driver you would typically first make the members that hold the values associated with your instrument, these members would then be inserted into vectors, and the vectors into a Device.

Your Driver object, subclassed from IPyDriver, would then contain these devices.

Text
^^^^

.. autoclass:: indipydriver.TextMember

.. autoclass:: indipydriver.TextVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers


Lights
^^^^^^

.. autoclass:: indipydriver.LightMember

.. autoclass:: indipydriver.LightVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers


Switches
^^^^^^^^

.. autoclass:: indipydriver.SwitchMember

.. autoclass:: indipydriver.SwitchVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers


Numbers
^^^^^^^

.. autoclass:: indipydriver.NumberMember
   :members: getfloatvalue, getformattedvalue, format_number

.. autoclass:: indipydriver.NumberVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers, getfloatvalue, getformattedvalue


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

.. autoclass:: indipydriver.BLOBMember

.. autoclass:: indipydriver.BLOBVector
   :members: send_delProperty, send_defVector, send_setVectorMembers, set_blobsize

Note that BLOBVectors do not have a send_setVector method, it is considered the more explicit send_setVectorMembers should always be used for BLOB's.
