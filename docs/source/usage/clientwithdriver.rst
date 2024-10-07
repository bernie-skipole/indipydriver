Driver with Client
==================

It is possible to import ConsoleClient from indipyclient.console to run the terminal client, and a driver with instrument in a single script. The example below imports 'make_driver' and ThermalControl from example1, and also the ConsoleClient, and runs their co-routines together::

    import asyncio

    from indipyclient.console import ConsoleClient
    from example1 import make_driver

    async def main(client, driver):
        """Run the client and driver"""

        try:

            # start the driver
            drivertask = asyncio.create_task( driver.asyncrun() )

            # start the client, and wait for it to close
            await client.asyncrun()

            # ask the driver to stop
            driver.shutdown()

            # wait for the driver to shutdown
            await drivertask

        except asyncio.CancelledError:
            # avoid outputting stuff on the command line
            pass
        finally:
            # clear the curses terminal setup
            client.console_reset()


    if __name__ == "__main__":

        # make a driver for the thermostat
        thermodriver = make_driver("Thermostat", 15)
        # set driver listening on localhost
        thermodriver.listen()
        # create a ConsoleClient calling localhost
        client = ConsoleClient()
        # run all coroutines
        asyncio.run( main(client, thermodriver) )


For more information on ConsoleClient, see the indipyclient documentation, in particular:

https://indipyclient.readthedocs.io/en/latest/usage/consoleclient.html
