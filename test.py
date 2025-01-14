
"sends a vector with four lights binary counting"


import asyncio
import indipydriver as ipd


class BinDriver(ipd.IPyDriver):
    """IPyDriver is subclassed here
       It has device 'bincounter' with a light 'binvector'
       with four members 'binvalue0' to 'binvalue3'
       which it populates with counting binary lights"""

    async def hardware(self):
        """Sends the counting binvector with four members
           showing red lights (Alert) for binary 1
           and green lights (Ok) for binary 0"""

        devicename = self.driverdata['devicename']

        binvector = self[devicename]['binvector']
        while not self.stop:
            # send a new lights count every second
            for n in range(16):
                await asyncio.sleep(1)
                binstring = f'{n:04b}'       # strings "0000" to "1111" generated as n increments
                binvector['binvalue0'] = "Alert" if binstring[3] == "1" else "Ok"
                binvector['binvalue1'] = "Alert" if binstring[2] == "1" else "Ok"
                binvector['binvalue2'] = "Alert" if binstring[1] == "1" else "Ok"
                binvector['binvalue3'] = "Alert" if binstring[0] == "1" else "Ok"
                await binvector.send_setVector()


def make_driver(devicename):
    "Returns an instance of the driver"

    # create four LightMembers, binvalue0 to binvalue3
    members= []
    for m in range(4):
        members.append( ipd.LightMember( name = f"binvalue{m}",
                                         label = f"Light {m}" )  )


    # create a vector containing these members
    binvector = ipd.LightVector( name="binvector",
                                 label="Light Counter",
                                 group="Values",
                                 state="Ok",
                                 lightmembers=members )

    # create a device with this vector
    bincounter = ipd.Device( devicename=devicename,
                             properties=[binvector] )

    # Create the Driver, containing this Device
    driver = BinDriver( bincounter, devicename=devicename )

    # and return the driver
    return driver


async def main():

    driver = make_driver("bincounter")
    server = ipd.IPyServer(driver)
    t = asyncio.create_task(server.asyncrun())
    print(f"Running {__file__}")
    await asyncio.sleep(10)
    print("Stopping")
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass
    print("Stopped")





if __name__ == "__main__":

    # serve the driver on localhost, port 7624
    asyncio.run(main())

