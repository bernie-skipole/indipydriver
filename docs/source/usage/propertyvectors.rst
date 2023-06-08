PropertyVectors
===============

A property vector is an object containing one or more 'members'.  For example a NumberVector will contain one or more NumberMember objects, each containing a number value.

This section documents the property vectors created and set into the device, and also the associated members.

All these vectors have arguments name, label, group, perm, state, except for LightVector which does not have perm (being a read only value).

name is the vector name

label is a string which can be used by the client, if not given it will be set equal to the name.

group is a further label used by the client, which can be used to group properties together. It can be left blank if not used.

perm is the permission - set to one of 'ro', 'wo', 'rw' - so 'ro' means the client can only read the vector values, not set them.

state is the state of the vector, and is an attribute which can be set before calling a send_setVector method to inform the client of the state of the property.

state can be set to one of 'Idle', 'Ok', 'Busy', 'Alert'.

Each vector is also a mapping, of vectorname:memberVALUE  - note, not member object, rather it is the value held by the member. In the thermostat example, the temperature of the vector member is set by

vector['temperature'] = TEMPERATURE

Where 'temperature' is the name of the member object and TEMPERATURE is a numeric value.

Each member has a name and label, again label is a string which can be used by the client, if not given it will be set equal to the name.

TextVector
^^^^^^^^^^

.. autoclass:: indipydriver.TextVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers

A TextVector takes one or more TextMember objects.

.. autoclass:: indipydriver.TextMember

LightVector
^^^^^^^^^^^

.. autoclass:: indipydriver.LightVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers

A LightVector takes one or more LightMember objects.

.. autoclass:: indipydriver.LightMember

For example, if a LightMember name is 'Indicator' it could be set with:

vector['Indicator'] = 'Ok'

await vector.send_setVector()

where vector is the vector object containing the Indicator.

SwitchVector
^^^^^^^^^^^^

.. autoclass:: indipydriver.SwitchVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers

A SwitchVector takes one or more SwitchMember objects.

.. autoclass:: indipydriver.SwitchMember

NumberVector
^^^^^^^^^^^^

.. autoclass:: indipydriver.NumberVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers

A NumberVector takes one or more NumberMember objects.

.. autoclass:: indipydriver.NumberMember

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


BLOBVector
^^^^^^^^^^

.. autoclass:: indipydriver.BLOBVector
   :members: send_delProperty, send_defVector, send_setVector, send_setVectorMembers

A BLOBVector takes one or more BLOBMember objects.

.. autoclass:: indipydriver.BLOBMember
