
import asyncio

from indipyclient import IPyClient

from indipyclient.events import getProperties


class RemoteConnection(IPyClient):


    def __init__(self, indihost, indiport, **clientdata):
        "Provides a connection to remote indi servers"

        IPyClient.__init__(self, indihost, indiport, **clientdata)
        # do not add info to client messages
        self.enable_reports = False
        # a list of devicenames that have blobenable sent
        self.clientdata["blobenablesent"] = []

    async def hardware(self):
        """If connection fails, clear blobenablesent list"""
        while not self._stop:
            await asyncio.sleep(0)
            if not self.connected:
                self.clientdata["blobenablesent"].clear()


    async def rxevent(self, event):
        "Handle events as they are received on this connection"
        rxdata = event.root
        if rxdata is None:
            return

        devicename = event.devicename
        vectorname = event.vectorname

        # rxdata is the xml data received

        if event.eventtype == "Define" or event.eventtype == "DefineBLOB":
            # on receiving a define vector, send the blobenabled status for that device
            # but record it, so it is not being sent repeatedly
            if devicename and (devicename in self) and (not (devicename in self.clientdata["blobenablesent"])):
                self.send_enableBLOB(self.clientdata["blob_enable"], devicename)
                self.clientdata["blobenablesent"].append(devicename)

        # check for a getProperties event, record what is being snooped
        if isinstance(event, getProperties):
            if devicename is None:
                self.clientdata["snoopall"] = True
            elif vectorname is None:
                self.clientdata["snoopdevices"].add(devicename)
            else:
                self.clientdata['snoopvectors'].add((devicename,vectorname))

            # if getproperties is targetted at a known device, send it to that device
            if devicename:
                if devicename in self.clientdata["devices"]:
                    # this getProperties request is meant for an attached device
                    await self.clientdata["devices"][devicename].driver.readerque.put(rxdata)
                    # no need to transmit this anywhere else
                    return
                for remcon in self.clientdata["remotes"]:
                    if remcon is self:
                        continue
                    if devicename in remcon:
                        # this getProperties request is meant for a remote connection
                        remcon.send(rxdata)
                        # no need to transmit this anywhere else
                        return

        # transmit rxdata out to other remote connections
        # which occurs if they are snooping on devices on this link.
        for remcon in self.clientdata["remotes"]:
            if remcon is self:
                continue
            if isinstance(event, getProperties):
                # either no devicename, or an unknown device
                # if it were a known devicename the previous block would have handled it.
                # so send it on all connections
                remcon.send(rxdata)
            else:
                # Check if this remcon is snooping on this device/vector
                if remcon.clientdata["snoopall"]:
                    remcon.send(rxdata)
                elif devicename and (devicename in remcon.clientdata["snoopdevices"]):
                    remcon.send(rxdata)
                elif devicename and vectorname and ((devicename, vectorname) in remcon.clientdata["snoopvectors"]):
                    remcon.send(rxdata)

        # transmit rxdata out to drivers
        for driver in self.clientdata["drivers"]:
            if isinstance(event, getProperties):
                # either no devicename, or an unknown device
                await driver.readerque.put(rxdata)
            else:
                # Check if this driver is snooping on this device/vector
                if driver.snoopall:
                    await driver.readerque.put(rxdata)
                elif devicename and (devicename in driver.snoopdevices):
                    await driver.readerque.put(rxdata)
                elif devicename and vectorname and ((devicename, vectorname) in driver.snoopvectors):
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
                await serverwriterque.put(rxdata)
                break
