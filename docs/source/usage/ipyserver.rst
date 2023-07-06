IPyServer
=========

In the current version 0.0.5, the IPyServer object is still being developed.

.. autoclass:: indipydriver.IPyServer
   :members: asyncrun


Assuming you have two importable modules, thermostat.py and windowcontrol.py::


    import asyncio

    from indipydriver import IPyServer

    import thermostat, windowcontrol

    driver1 = thermostat.make_driver()

    driver2 = windowcontrol.make_driver()

    server = IPyServer([driver1, driver2])

    asyncio.run(server.asyncrun())
