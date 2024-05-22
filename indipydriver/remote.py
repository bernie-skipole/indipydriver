import sys

sys.path.insert(0, "/home/bernard/git/indipyclient")


import asyncio

from indipyclient import IPyClient

from indipyclient.events import getProperties


class RemoteConnection(IPyClient):


    def __init__(self, indihost, indiport, **clientdata):
        "Provides a connection to remote indi servers"

        IPyClient.__init__(self, indihost, indiport, **clientdata)
        # do not add info to client messages
        self.enable_reports = False


    async def rxevent(self, event):
        "Handle events as they are received on this connection"
        rxdata = event.root
        if rxdata is None:
            return

        # rxdata is the xml data received

        # check for a getProperties event, record what is being snooped
        if isinstance(event, getProperties):
            if event.devicename is None:
                self.clientdata["snoopall"] = True
            elif event.vectorname is None:
                self.clientdata["snoopdevices"].append(event.devicename)
            else:
                self.clientdata['snoopvectors'].append((event.devicename,event.vectorname))

            # if getproperties is targetted at a known device, send it to that device
            if event.devicename:
                if event.devicename in self.clientdata["devices"]:
                    # this getProperties request is meant for an attached device
                    await self.clientdata["devices"][event.devicename].driver.readerque.put(rxdata)
                    # no need to transmit this anywhere else
                    return
                for remcon in self.clientdata["remotes"]:
                    if remcon is self:
                        continue
                    if event.devicename in remcon:
                        # this getProperties request is meant for a remote connection
                        remcon.send(rxdata)
                        # no need to transmit this anywhere else
                        return

        # transmit rxdata out to other connections if they are snooping,
        # or if a getProperties is received for an unknown device
        for remcon in self.clientdata["remotes"]:
            if remcon is self:
                continue
            if isinstance(event, getProperties):
                remcon.send(rxdata)
            elif remcon.clientdata["snoopall"]:
                remcon.send(rxdata)
            elif event.devicename and (event.devicename in remcon.clientdata["snoopdevices"]):
                remcon.send(rxdata)
            elif event.devicename and event.vectorname and ((event.devicename, event.vectorname) in remcon.clientdata["snoopvectors"]):
                remcon.send(rxdata)

        # transmit rxdata out to drivers if they are snooping, or if a getProperties is received
        for driver in self.clientdata["drivers"]:
            if isinstance(event, getProperties):
                await driver.readerque.put(rxdata)
            elif driver.snoopall:
                await driver.readerque.put(rxdata)
            elif event.devicename and (event.devicename in driver.snoopdevices):
                await driver.readerque.put(rxdata)
            elif event.devicename and event.vectorname and ((event.devicename, event.vectorname) in driver.snoopvectors):
                await driver.readerque.put(rxdata)

        # transmit rxdata out to clients
        serverwriterque = self.clientdata['serverwriterque']
        connectionpool = self.clientdata['connectionpool']

        # If no clients are connected, do not put this data into
        # the serverwriterque
        for clientconnection in connectionpool:
            if clientconnection.connected:
                # at least one is connected, so this data is put into
                # serverwriterque
                await self.serverwriterque.put(rxdata)
                break
