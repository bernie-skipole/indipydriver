
import asyncio, sys

import xml.etree.ElementTree as ET


class TX:
    "An object that transmits data"

    def __init__(self):
        self.writerque = None


    async def run_tx(self):
        """gets data from writerque, and transmits it"""
        # should be overridden by child class
        while True:
            await asyncio.sleep(0)
            if self.writerque:
                txdata = writerque.popleft()
                # and do something with it
                print( ET.tostring(txdata) )


class STDOUT_TX(TX):
    "An object that transmits data"

    async def run_tx(self):
        """gets data from writerque, and transmits it"""
        while True:
            await asyncio.sleep(0)
            # get block of data from writerque and transmit down stdout
            if self.writerque:
                txdata = self.writerque.popleft()
                # and send it out on stdout
                binarydata = ET.tostring(txdata)
                sys.stdout.buffer.write(binarydata)
                sys.stdout.buffer.flush()
