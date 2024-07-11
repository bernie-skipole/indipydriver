Driver with Client
==================

It is possible to import ConsoleClient from indipyclient.console to run the terminal client, and a driver in a single script. The example below imports 'make_driver' from example1, and also the ConsoleClient, and runs both together. Note that the client.stopped attribute is used to shut down the driver when quit is chosen on the client::


    import asyncio

    from indipyclient.console import ConsoleClient
    from example1 import make_driver


    async def monitor(client, driver):
        "This monitors the client, if it shuts down, it shuts down the driver"
        await client.stopped.wait()
        # the client has stopped, shut down the driver
        driver.shutdown()


    async def main(client, driver):
        "Run the driver and client together"
        try:
            await asyncio.gather(client.asyncrun(), driver.asyncrun(), monitor(client, driver))
        except asyncio.CancelledError:
            # avoid outputting stuff on the command line
            pass
        finally:
            # clear curses setup
            client.console_reset()


    if __name__ == "__main__":

        # Get driver, in this case from example1
        driver = make_driver()
        # set driver listening on localhost
        driver.listen()
        # create a ConsoleClient calling localhost
        client = ConsoleClient()
        # run them
        asyncio.run(main(client, driver))


For more information on ConsoleClient, see the indipyclient documentation, in particular:

https://indipyclient.readthedocs.io/en/latest/usage/consoleclient.html
