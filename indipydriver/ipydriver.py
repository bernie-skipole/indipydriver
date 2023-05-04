

import collections

import asyncio

from .receiver import STDIN_RX
from .transmitter import STDOUT_TX
from . import events


class IPyDriver:

    """To run this driver, create an IPyDriver instance, and then
       its awaitable asyncrun method should be run in an async loop.
       """

    def __init__(self, devices, tx=None, rx=None):

        # this is a dictionary of device name to device this driver owns
        self.devices = {d.devicename:d for d in devices}

        # data is transmitted out on the writerque
        self.writerque = collections.deque()
        # and read in from the readerque
        self.readerque = collections.deque()

        # the tx object needs the writerque to obtain outgoing data
        # which it then transmitts
        if tx is None:
            self._tx = STDOUT_TX()
        else:
            self._tx = tx
        self._tx.writerque = self.writerque

        # the rx object needs the readerque into which it sets incoming data
        if rx is None:
            self._rx = STDIN_RX()
        else:
            self._rx = rx
        self._rx.readerque = self.readerque


    @property
    def rx(self):
        return self._rx

    @rx.setter
    def rx(self, rx):
        self._rx = rx
        self._rx.readerque = self.readerque

    @property
    def tx(self):
        return self._tx

    @tx.setter
    def tx(self, tx):
        self._tx = tx
        self._tx.writerque = self.writerque

    async def _read_readerque(self):
        while True:
            await asyncio.sleep(0)
            # reads readerque, and sends xml data to the device via its dataque
            if self.readerque:
                root = self.readerque.popleft()
                if root.tag == "getProperties":
                    version = root.get("version")
                    if version != "1.7":
                        continue
                    # getProperties received with correct version
                    devicename = root.get("device")
                    # devicename is None (for all devices), or a named device
                    if devicename is None:
                        for d in self.devices.values():
                            d.dataque.append(root)
                    elif devicename in self.devices:
                        self.devices[devicename].dataque.append(root)
                    else:
                        # device not recognised
                        continue
                else:
                    # root.tag will be either newSwitchVector, newNumberVector,.. etc
                    devicename = root.get("device")
                    if devicename is None:
                        # device not given, ignore this
                        continue
                    elif devicename in self.devices:
                        self.devices[devicename].dataque.append(root)
                    else:
                        # device not recognised
                        continue

    async def hardware(self):
        "Override this, typically uses a while loop to control device hardware"
        while True:
            await asyncio.sleep(0)

    async def eventaction(self, event):
        """On receiving data, this is called, and should handle any necessary actions
           This should be replaced in child classes.
           event is an object describing the event, with attributes
           devicename, vectorname, vector,
           where vector is the properties vector causing the event
           set any attributes of vector required, and if a reply is to be sent
           call event.send(timestamp, timeout, message)
           timestamp is a datetime object, if not given will default to utcnow
           timeout is seconds data is valid, if not given will default to zero which impies value not used
           message is any message to be sent
           to send the xml associated with the event."""
        await asyncio.sleep(0)
        match event:
            case events.getProperties():
                # on receiving a getProperties event, a reply should be sent
                event.send()

    async def asyncrun(self):
        """Gathers tasks to be run simultaneously"""

        device_handlers = []
        property_handlers = []
        for device in self.devices.values():
            device_handlers.append(device.handler())
            for pv in device.propertyvectors.values():
                property_handlers.append(pv.handler())
                # also give the propertyvector a reference to this driver
                # so it can call eventaction and have access to writerque
                pv.driver = self

        await asyncio.gather(self._rx.run_rx(),      # task in _rx object to get incoming xml data and pass to this driver
                             self._tx.run_tx(),      # task in _tx object to transmit xml data
                             self._read_readerque(), # task to handle received xml data
                             self.hardware(),        # task to operate device hardware
                             *device_handlers,       # each device handles its incoming data
                             *property_handlers      # each property handles its incoming data
                            )


class Device:

    def __init__(self, devicename, properties, tx=None, rx=None):

        # This device name
        self.devicename = devicename

        # the driver places data in this que to send data to this device
        self.dataque = collections.deque()

        # Every property of this device has a dataque, which is set into this dictionary
        self.propertyquedict = {p.name:p.dataque for p in properties}

        # this is a dictionary of property name to propertyvector this device owns
        self.propertyvectors = {}
        for p in properties:
            p.propertyquedict = self.propertyquedict
            p.devicename = self.devicename
            self.propertyvectors[p.name] = p

    async def handler(self):
        """Handles data read from readerque"""
        while True:
            # get block of data from the self.dataque
            await asyncio.sleep(0)
            if self.dataque:
                root = self.dataque.popleft()
                if root.tag == "getProperties":
                    name = root.get("name")
                    # name is None (for all properties), or a named property
                    if name is None:
                        for pname,pvector in self.propertyvectors.items():
                            pvector.dataque.append(root)
                    elif name in self.propertyvectors:
                        self.propertyvectors[name].dataque.append(root)
                    else:
                        # property name not recognised
                        continue
                elif root.tag == "enableBLOB":
                    name = root.get("name")
                    # name is None (for all properties), or a named property
                    if name is None:
                        for pname,pvector in self.propertyvectors.items():
                            pvector.dataque.append(root)
                    elif name in self.propertyvectors:
                        self.propertyvectors[name].dataque.append(root)
                    else:
                        # property name not recognised
                        continue
                else:
                    # root.tag will be either newSwitchVector, newNumberVector,.. etc
                    name = root.get("name")
                    if name is None:
                        # name not given, ignore this
                        continue
                    elif name in self.propertyvectors:
                        self.propertyvectors[name].dataque.append(root)
                    else:
                        # property name not recognised
                        continue
