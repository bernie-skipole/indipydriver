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

        devicename = event.devicename
        vectorname = event.vectorname

        # rxdata is the xml data received

        # check for a getProperties event, record what is being snooped
        if isinstance(event, getProperties):
            if devicename is None:
                self.clientdata["snoopall"] = True
            elif vectorname is None:
                self.clientdata["snoopdevices"].append(devicename)
            else:
                self.clientdata['snoopvectors'].append((devicename,vectorname))

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

        # transmit rxdata out to other connections
        for remcon in self.clientdata["remotes"]:
            if remcon is self:
                continue
            if devicename and (devicename in remcon):
                # this devicename has been found on this remote
                # data is intended for this connection
                # it is not snoopable, since it is data to a device, not from it.
                remcon.send(rxdata)
            elif isinstance(event, getProperties):
                # either no devicename, or an unknown device
                # if it were a known devicename the previous block would have handled it.
                # so send it on all connections
                remcon.send(rxdata)
            elif not xmldata.tag.startswith("new"):
                # either devicename is unknown, or this data is to/from another driver.
                # So check if this remcon is snooping on this device/vector
                # only forward def's and set's, not 'new' vectors which
                # do not come from a device, but only from a client to the target device.
                if remcon.clientdata["snoopall"]:
                    remcon.send(rxdata)
                elif devicename and (devicename in remcon.clientdata["snoopdevices"]):
                    remcon.send(rxdata)
                elif devicename and vectorname and ((devicename, vectorname) in remcon.clientdata["snoopvectors"]):
                    remcon.send(rxdata)

        # transmit rxdata out to drivers
        for driver in self.clientdata["drivers"]:
            if devicename and (devicename in driver):
                # data is intended for this driver
                # it is not snoopable, since it is data to a device, not from it.
                await driver.readerque.put(rxdata)
            elif isinstance(event, getProperties):
                # either no devicename, or an unknown device
                await driver.readerque.put(rxdata)
            elif not rxdata.tag.startswith("new"):
                # either devicename is unknown, or this data is to/from another driver.
                # So check if this driver is snooping on this device/vector
                # only forward def's and set's, not 'new' vectors which
                # do not come from a device, but only from a client to the target device.
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
