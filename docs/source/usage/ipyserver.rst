IPyServer
=========

This server class is used to run IPyDriver instances and create a listening port service. It provides the snooping ability between drivers, enables connections to other remote INDI servers so a branching tree network of drivers can be made, it implements enableBLOB instructions received from the client, and allows up to ten client connections.


.. autoclass:: indipydriver.IPyServer
   :members: asyncrun, add_remote


Assuming you have two importable modules containing drivers, thermostat.py and windowcontrol.py::


    import asyncio

    from indipydriver import IPyServer

    import thermostat, windowcontrol

    driver1 = thermostat.make_driver()

    driver2 = windowcontrol.make_driver()

    server = IPyServer([driver1, driver2])

    asyncio.run(server.asyncrun())

This example would run the drivers together with the server.  Using the above example, up to five clients can connect to localhost, port 7624, these being the defaults.
