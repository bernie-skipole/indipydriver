
import collections

import asyncio

import xml.etree.ElementTree as ET

from .events import getProperties


class PropertyVector:
    "Parent class of SwitchVector etc.."

    def __init__(self, name):
        self.name = name
        # if self.enable is False, this property is dormant
        self.enable = True
        # the device places data in this dataque
        # for the vector to act upon
        self.dataque = collections.deque()

        # this will be set when the driver asyncrun is run
        self.driver = None


    def set_propertyquedict(self, propertyquedict):
        """Every PropertyVector has access to the dataque of
           all other propertyvectors via this dictionary, which is
           a name:dataque dictionary"""
        self.propertyquedict = propertyquedict


    def send_defVector(timestamp, timeout, message):
        "overridden in child classes"
        pass


    async def handler(self):
        """Check received data and take action"""
        # xmldata to be sent is to be generated here
        while True:
            await asyncio.sleep(0)
            if not self.enable:
                await asyncio.sleep(0.1)
                continue
            # test if any xml data has been received
            if not self.dataque:
                continue
            root = self.dataque.popleft()
            if root.tag == "getProperties":
                # create event
                event = getProperties(self.devicename, self.name, self)
                await self.driver.eventaction(event)
                continue
            else:
                # further elifs should go here
                pass


class SwitchVector(PropertyVector):

    def __init__(self, name, label, group, perm, rule, state, switches):
        super().__init__(name)
        self.label = label
        self.group = group
        self.perm = perm
        self.rule = rule
        self.state = state
        # this is a dictionary of switch name : switch
        self.switches = {switch.name:switch for switch in switches}

    def __getitem__(self, switchname):
        return self.switches[switchname]

    def send_defVector(self, timestamp, timeout, message):
        """Sets defSwitchVector into writerque"""
        xmldata = ET.Element('defSwitchVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("group", self.group)
        xmldata.set("perm", self.perm)
        xmldata.set("rule", self.rule)
        # note - limit timestamp characters to :21 to avoid long fractions of a second
        xmldata.set("timestamp", timestamp.isoformat(sep='T')[:21])
        xmldata.set("timeout", str(timeout))
        if message:
            xmldata.set("message", message)
        for switch in self.switches.values():
            xmldata.append(switch.defswitch())
        self.driver.writerque.append(xmldata)
