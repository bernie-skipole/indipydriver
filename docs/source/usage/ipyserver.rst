IPyServer
=========

In the current version 0.0.6, the IPyServer object is still being developed.

enableBLOBs is implemented

snooping between drivers is not yet done.


.. autoclass:: indipydriver.IPyServer
   :members: asyncrun


Assuming you have two importable modules containing the previous examples, thermostat.py and windowcontrol.py::


    import asyncio

    from indipydriver import IPyServer

    import thermostat, windowcontrol

    driver1 = thermostat.make_driver()

    driver2 = windowcontrol.make_driver()

    server = IPyServer([driver1, driver2])

    asyncio.run(server.asyncrun())

This example would run the drivers together with the server, each driver.asyncrun() method should not be called, nor should the driver.listen() method - as IPyServer is doing the port communications.  Using the above example, up to five (the default) clients can connect to localhost, 7624.
