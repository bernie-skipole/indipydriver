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

A TextVector is used to send and receive text between instrument and client.

.. autoclass:: indipydriver.TextVector
   :members:

   .. method:: send_delProperty(message="", timestamp=None)

      Informs the client this vector is not available, it also sets a vector.enable attribute to
      False, which stops any data being transmitted between the client and this property vector.
      Setting vector.enable to True re-enables communications.
      The message argument is any appropriate string which the client could display to the user.
      The timestamp should be either None or a datetime.datetime object. If the timestamp is None
      a datetime.datetime.utcnow() value will be inserted.

.. autoclass:: indipydriver.TextMember

LightVector
^^^^^^^^^^^

A LightVector is an instrument indicator, and sends one or more members with values 'Idle', 'Ok', 'Busy' or 'Alert'. In general a client will indicate this state with different colours.

.. autoclass:: indipydriver.LightVector
   :members:

   .. method:: send_delProperty(message="", timestamp=None)

      Informs the client this vector is not available, it also sets a vector.enable attribute to
      False, which stops any data being transmitted between the client and this property vector.
      Setting vector.enable to True re-enables communications.
      The message argument is any appropriate string which the client could display to the user.
      The timestamp should be either None or a datetime.datetime object. If the timestamp is None
      a datetime.datetime.utcnow() value will be inserted.

.. autoclass:: indipydriver.LightMember

A LightMember can only have one of 'Idle', 'Ok', 'Busy' or 'Alert' values, so if a LightMember name is 'Indicator' it could be set with:

vector['Indicator'] = 'Ok'

vector.send_defVector()

where vector is the vector object containing the Indicator.

SwitchVector
^^^^^^^^^^^^

.. autoclass:: indipydriver.SwitchVector
   :members:

   .. method:: send_delProperty(message="", timestamp=None)

      Informs the client this vector is not available, it also sets a vector.enable attribute to
      False, which stops any data being transmitted between the client and this property vector.
      Setting vector.enable to True re-enables communications.
      The message argument is any appropriate string which the client could display to the user.
      The timestamp should be either None or a datetime.datetime object. If the timestamp is None
      a datetime.datetime.utcnow() value will be inserted.

A SwitchVector takes one or more SwitchMember objects.

.. autoclass:: indipydriver.SwitchMember

NumberVector
^^^^^^^^^^^^

.. autoclass:: indipydriver.NumberVector
   :members:

   .. method:: send_delProperty(message="", timestamp=None)

      Informs the client this vector is not available, it also sets a vector.enable attribute to
      False, which stops any data being transmitted between the client and this property vector.
      Setting vector.enable to True re-enables communications.
      The message argument is any appropriate string which the client could display to the user.
      The timestamp should be either None or a datetime.datetime object. If the timestamp is None
      a datetime.datetime.utcnow() value will be inserted.

.. autoclass:: indipydriver.NumberMember


BLOBVector
^^^^^^^^^^

.. autoclass:: indipydriver.BLOBVector
   :members:

   .. method:: send_delProperty(message="", timestamp=None)

      Informs the client this vector is not available, it also sets a vector.enable attribute to
      False, which stops any data being transmitted between the client and this property vector.
      Setting vector.enable to True re-enables communications.
      The message argument is any appropriate string which the client could display to the user.
      The timestamp should be either None or a datetime.datetime object. If the timestamp is None
      a datetime.datetime.utcnow() value will be inserted.

.. autoclass:: indipydriver.BLOBMember
