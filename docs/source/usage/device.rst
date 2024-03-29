Device
======

.. autoclass:: indipydriver.Device
   :members:

The Device is also a mapping, of vectorname:vectorobject, so to access a vector you could use device['vectorname'].

The device has attributes:

**devicename**

The given name of the device, this device object can be accessed from the driver as driver[devicename]

**enable**

Automatically set to False if the device is deleted by calling the device send_delProperty() method. The attribute should be set to True to re-enable the device, also for every property of the device, you will need to call the vector send_defVector() method to inform the client that the device and its properties are now available.

**devicedata**

Set from the device constructer as optional keyword arguments, can be used to pass in hardware data to the device object.

**driver**

The driver object, can be used to access driver.send_message() and driver.send_getProperties() methods if required, and also to access any other device using the driver mapping feature.
