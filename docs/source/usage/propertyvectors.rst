PropertyVectors
===============

A property vector is an object containing one or more 'members'.  A NumberVector will contain one or more NumberMember objects, each containing a number value.

All these vectors have arguments xyx

The vector is also a mapping, of vectorname:memberVALUE  - note, not member object, rather it is the value held by the member. In the thermostat example, the temperature of the vector member is set by vector['temperature'] = TEMPERATURE, where 'temperature' is the name of the member object.



.. autoclass:: indipydriver.NumberVector
   :members:


.. autoclass:: indipydriver.SwitchVector
   :members:
