
import asyncio

import xml.etree.ElementTree as ET

from datetime import datetime, timezone

import logging
logger = logging.getLogger(__name__)

from .remotelink import IPyClient

from .remotelink.events import getProperties


class RemoteConnection(IPyClient):


    def __init__(self, indihost, indiport, **clientdata):
        "Provides a connection to remote indi servers"

        IPyClient.__init__(self, indihost, indiport, **clientdata)
        # do not add info to client messages
        self.enable_reports = False
        # a list of devicenames that have blobenable sent
        self.clientdata["blobenablesent"] = []

    async def hardware(self):
        """If connection fails, clear blobenablesent list
           and for each device learnt, disable it"""
        serverwriterque = self.clientdata['serverwriterque']
        connectionpool = self.clientdata['connectionpool']
        isconnected = False
        while not self._stop:
            await asyncio.sleep(0.1)
            if self.connected:
                if isconnected:
                    continue
                isconnected = True
                # a new connection has been made
                await self.send_getProperties()
                for clientconnection in connectionpool:
                    if clientconnection.connected:
                        # a client is connected, send a message
                        timestamp = datetime.now(tz=timezone.utc)
                        timestamp = timestamp.replace(tzinfo = None)
                        tstring = timestamp.isoformat(sep='T')
                        messagedata = ET.Element('message')
                        messagedata.set("timestamp", tstring)
                        messagedata.set("message", f"Remote connection made to {self.indihost}:{self.indiport}")
                        await self.queueput(serverwriterque, messagedata)
                        break
                continue
            # The connection has failed
            isconnected = False
            self.clientdata["blobenablesent"].clear()
            if self.enabledlen():
                # some devices are enabled, disable them
                timestamp = datetime.now(tz=timezone.utc)
                timestamp = timestamp.replace(tzinfo = None)
                tstring = timestamp.isoformat(sep='T')
                # If no clients are connected, do not send data into
                # the serverwriterque
                clientconnected = False
                for clientconnection in connectionpool:
                    if clientconnection.connected:
                        clientconnected = True
                        break
                # send a message
                if clientconnected:
                    messagedata = ET.Element('message')
                    messagedata.set("timestamp", tstring)
                    messagedata.set("message", f"Remote connection to {self.indihost}:{self.indiport} lost")
                    await self.queueput(serverwriterque, messagedata)
                for devicename, device in self.items():
                    if device.enable:
                        device.disable()
                        if clientconnected:
                            xmldata = ET.Element('delProperty')
                            xmldata.set("device", devicename)
                            xmldata.set("timestamp", tstring)
                            xmldata.set("message", f"Remote Connection lost, {devicename} disabled")
                            await self.queueput(serverwriterque, xmldata)


    async def rxevent(self, event):
        "Handle events as they are received on this connection"
        rxdata = event.root
        if rxdata is None:
            return

        devicename = event.devicename
        vectorname = event.vectorname

        # rxdata is the xml data received

        if event.eventtype == "Define" or event.eventtype == "DefineBLOB":
            # check for duplicate devicename
            for driver in self.clientdata["alldrivers"]:
                if devicename in driver:
                    logger.error(f"A duplicate devicename {devicename} has been detected")
                    await self.queueput(self.clientdata['serverwriterque'], None)
                    return
            for remcon in self.clientdata["remotes"]:
                if remcon is self:
                    continue
                if devicename in remcon:
                    logger.error(f"A duplicate devicename {devicename} has been detected")
                    await self.queueput(self.clientdata['serverwriterque'], None)
                    return
            # on receiving a define vector, send the blobenabled status for that device
            # but record it, so it is not being sent repeatedly
            if devicename and (not (devicename in self.clientdata["blobenablesent"])):
                await self.send_enableBLOB(self.clientdata["blob_enable"], devicename)
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
                for driver in self.clientdata["alldrivers"]:
                    if devicename in driver:
                        # this getProperties request is meant for an attached device
                        await self.queueput(driver.readerque, rxdata)
                        # no need to transmit this anywhere else
                        return
                for remcon in self.clientdata["remotes"]:
                    if remcon is self:
                        continue
                    if devicename in remcon:
                        # this getProperties request is meant for a remote connection
                        await remcon.send(rxdata)
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
                await remcon.send(rxdata)
            else:
                # Check if this remcon is snooping on this device/vector
                if remcon.clientdata["snoopall"]:
                    await remcon.send(rxdata)
                elif devicename and (devicename in remcon.clientdata["snoopdevices"]):
                    await remcon.send(rxdata)
                elif devicename and vectorname and ((devicename, vectorname) in remcon.clientdata["snoopvectors"]):
                    await remcon.send(rxdata)

        # transmit rxdata out to drivers
        for driver in self.clientdata["alldrivers"]:
            if isinstance(event, getProperties):
                # either no devicename, or an unknown device
                await self.queueput(driver.readerque, rxdata)
            else:
                # Check if this driver is snooping on this device/vector
                if driver.snoopall:
                    await self.queueput(driver.readerque, rxdata)
                elif devicename and (devicename in driver.snoopdevices):
                    await self.queueput(driver.readerque, rxdata)
                elif devicename and vectorname and ((devicename, vectorname) in driver.snoopvectors):
                    await self.queueput(driver.readerque, rxdata)

        # transmit rxdata out to clients
        serverwriterque = self.clientdata['serverwriterque']
        connectionpool = self.clientdata['connectionpool']

        # If no clients are connected, do not put this data into
        # the serverwriterque
        for clientconnection in connectionpool:
            if clientconnection.connected:
                # at least one is connected, so this data is put into
                # serverwriterque
                await self.queueput(serverwriterque, rxdata)
                break
