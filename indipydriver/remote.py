import sys

sys.path.insert(0, "/home/bernard/git/indipyclient")


import asyncio

from indipyclient import IPyClient


class RemoteConnection(IPyClient):


    def __init__(self, host, port, debug_enable=False):
        "An instance of this is a mapping of devicename to device object"

        IPyClient.__init__(self, indihost=host, indiport=port)
        self._verbose = 2
        self.enable_reports = False


    async def rxevent(self, event):
        "Gets events as they are received"

        xmldata = event.root
