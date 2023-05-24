IPyDriver
=========

.. autoclass:: indipydriver.IPyDriver
   :members:

The driver is also a mapping, of devicename:deviceobject, so your code in the hardware or clientevent methods could access a specific device using self['devicename'].

Similarly a Device object is a mapping to a vector, so to access a vector you could use self['devicename']['vectorname'].

The 'snooping' capabilities enable one driver to receive data transmitted by another, possibly remote driver. For a simple instrument this will probably not be used.
