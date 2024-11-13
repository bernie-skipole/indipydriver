
import sys

from datetime import datetime, timezone

from base64 import standard_b64decode

from collections import UserDict

import xml.etree.ElementTree as ET

from . import propertyvectors

from .propertymembers import ParseException, getfloat



def _parse_timestamp(timestamp_string):
    """Parse a timestamp string and return either None on failure, or a datetime object
       If the given timestamp_string is None, return the datetime for the current time.
       Everything is UTC"""
    if timestamp_string:
        try:
            if '.' in timestamp_string:
                # remove fractional part, not supported by datetime.fromisoformat
                timestamp_string, remainder = timestamp_string.rsplit('.', maxsplit=1)
                if len(remainder) < 6:
                    remainder = "{:<06}".format(remainder)
                elif len(remainder) > 6:
                    remainder = remainder[:6]
                remainder = int(remainder)
                timestamp = datetime.fromisoformat(timestamp_string)
                timestamp = timestamp.replace(microsecond=remainder, tzinfo=timezone.utc)
            else:
                timestamp = datetime.fromisoformat(timestamp_string)
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except Exception:
            timestamp = None
    else:
        timestamp = datetime.now(tz=timezone.utc)
    return timestamp


class VectorTimeOut:
    """This event is generated by a timeout, not by received data."""

    def __init__(self, device, vector):
        self.device = device
        self.devicename = self.device.devicename
        self.vector = vector
        self.vectorname = self.vector.name
        self.timestamp = datetime.now(tz=timezone.utc)
        self.eventtype = "TimeOut"
        self.root = None


class Event:
    "Parent class for events received from drivers"
    def __init__(self, root, device, client):
        self.device = device
        self._client = client
        self.vectorname = None
        if device is None:
            self.devicename = None
        else:
            self.devicename = self.device.devicename
        self.root = root
        self.timestamp = _parse_timestamp(root.get("timestamp"))

    def __str__(self):
        return ET.tostring(self.root, encoding='unicode')



class Message(Event):
    """This contains attribute 'message' with the message string sent by the remote driver.
       Attribute devicename could be None if the driver is sending a system wide message."""

    def __init__(self, root, device, client):
        super().__init__(root, device, client)
        self.eventtype = "Message"
        self.message = root.get("message", "")
        if device is None:
            # state wide message
            client.messages.appendleft( (self.timestamp, self.message) )
        else:
            device.messages.appendleft( (self.timestamp, self.message) )


class getProperties(Event):
    """This may have a device and name, both may be None
       But there may still be a devicename and vectorname for an unknown device"""

    def __init__(self, root, device, client):
        super().__init__(root, device, client)
        self.eventtype = "getProperties"
        self.devicename = root.get("device")
        self.vectorname = root.get("name")


class delProperty(Event):
    """The remote driver is instructing the client to delete either a device or a vector property.
       This contains attribute vectorname, if it is None, then the whole device is to be deleted.
       A 'message' attribute contains any message sent by the client with this instruction.
       This event will automatically set the appropriate enable flag to False in the effected
       device and vectors."""

    def __init__(self, root, device, client):
        super().__init__(root, device, client)
        self.eventtype = "Delete"
        if self.devicename is None:
            raise ParseException("delProperty has no devicename")
        if not self.device.enable:
            # already deleted
            raise ParseException("device already deleted")
        self.vectorname = root.get("name")
        self.message = root.get("message", "")
        # properties is a dictionary of property name to propertyvector this device owns
        # This method updates a property vector and sets it into properties
        properties = device.data
        if self.vectorname:
            # does this vector already exist, if it does, disable it
            if self.vectorname in properties:
                vector = properties[self.vectorname]
                vector.enable = False
        else:
            # No vectorname given, disable all properties
            for vector in properties.values():
                vector.enable = False


class defVector(Event, UserDict):
    "Parent to def vectors, adds a mapping of membername:value"
    def __init__(self, root, device, client):
        Event.__init__(self, root, device, client)
        UserDict.__init__(self)
        self.eventtype = "Define"
        self.vectorname = root.get("name")
        if self.vectorname is None:
            raise ParseException("defVector has no vector name")
        self.label = root.get("label", self.vectorname)
        self.group = root.get("group", "DEFAULT GROUP")
        state = root.get("state")
        if not state:
            raise ParseException("defVector has no state given")
        if not state in ('Idle','Ok','Busy','Alert'):
            raise ParseException("defVector has invalid state")
        self.state = state
        self.message = root.get("message", "")


    def __setitem__(self, membername):
        raise KeyError


class defSwitchVector(defVector):

    """The remote driver has sent this to define a switch vector property, this
       is a mapping of membername:value"""

    def __init__(self, root, device, client):
        defVector.__init__(self, root, device, client)
        self.perm = root.get("perm")
        if self.perm is None:
            raise ParseException("defSwitchVector has no perm given")
        if self.perm not in ('ro', 'wo', 'rw'):
            raise ParseException("defSwitchVector has invalid perm")
        self.rule = root.get("rule")
        if self.rule is None:
            raise ParseException("defSwitchVector has no rule given")
        if self.rule not in ('OneOfMany', 'AtMostOne', 'AnyOfMany'):
            raise ParseException("defSwitchVector has invalid rule")
        try:
            timeout = root.get("timeout")
            if not timeout:
                self.timeout = 0.0
            else:
                self.timeout = float(timeout)
        except Exception:
            self.timeout = 0.0
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defSwitch":
                membername = member.get("name")
                if not membername:
                    raise ParseException("defSwitch member has no name")
                label = member.get("label", membername)
                self.memberlabels[membername] = label
                if not member.text:
                    raise ParseException("defSwitch member has invalid value")
                value = member.text.strip()
                if value == "On":
                    self.data[membername] = "On"
                elif value == "Off":
                    self.data[membername] = "Off"
                else:
                    raise ParseException("defSwitch member has invalid value")
            else:
                raise ParseException("defSwitchVector member has invalid tag")
        if not self.data:
            raise ParseException("defSwitchVector has no valid contents")

        # This method updates a property vector and sets it into the device 'data' dictionary
        # which is a dictionary of property name to propertyvector this device owns
        properties = device.data

        # does this vector already exist
        if self.vectorname in properties:
            self.vector = properties[self.vectorname]
            # set changed values into self.vector by calling vector._defvector
            # with this event as its argument
            self.vector._defvector(self)
        else:
            # create a new SwitchVector
            self.vector = propertyvectors.SwitchVector(self)
            # add it to properties
            properties[self.vectorname] = self.vector


class defTextVector(defVector):

    """The remote driver has sent this to define a text vector property, this
       is a mapping of membername:value."""

    def __init__(self, root, device, client):
        defVector.__init__(self, root, device, client)
        self.perm = root.get("perm")
        if self.perm is None:
            raise ParseException("No perm given in defTextVector")
        if self.perm not in ('ro', 'wo', 'rw'):
            raise ParseException("Invalid perm given in defTextVector")
        try:
            timeout = root.get("timeout")
            if not timeout:
                self.timeout = 0.0
            else:
                self.timeout = float(timeout)
        except Exception:
            self.timeout = 0.0
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defText":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing member name in defText")
                label = member.get("label", membername)
                self.memberlabels[membername] = label
                if not member.text:
                    value = ""
                else:
                    value = member.text.strip()
                self.data[membername] = value
            else:
                raise ParseException("Invalid tag in defTextVector")
        if not self.data:
            raise ParseException("No member values in defTextVector")

        # This method updates a property vector and sets it into the device 'data' dictionary
        # which is a dictionary of property name to propertyvector this device owns
        properties = device.data

        # does this vector already exist
        if self.vectorname in properties:
            self.vector = properties[self.vectorname]
            # set changed values into self.vector by calling vector._defvector
            # with this event as its argument
            self.vector._defvector(self)
        else:
            # create a new TextVector
            self.vector = propertyvectors.TextVector(self)
            # add it to properties
            properties[self.vectorname] = self.vector


class defNumberVector(defVector):

    """The remote driver has sent this to define a number vector property, this
       is a mapping of membername:value. Its attributes memberlabels gives further
       description of members, being a dictionary of
       membername:(label, format, min, max, step)."""

    def __init__(self, root, device, client):
        defVector.__init__(self, root, device, client)
        self.perm = root.get("perm")
        if self.perm is None:
            raise ParseException("No perm given in defNumberVector")
        if self.perm not in ('ro', 'wo', 'rw'):
            raise ParseException("Invalid perm given in defNumberVector")
        try:
            timeout = root.get("timeout")
            if not timeout:
                self.timeout = 0.0
            else:
                self.timeout = float(timeout)
        except Exception:
            self.timeout = 0.0
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and
        # value being a tuple of (label, format, min, max, step)
        self.memberlabels = {}
        for member in root:
            if member.tag == "defNumber":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing member name in defNumber")
                label = member.get("label", membername)
                memberformat = member.get("format")
                if not memberformat:
                    raise ParseException("Missing format in defNumber")
                membermin = member.get("min")
                if not membermin:
                    raise ParseException("Missing min value in defNumber")
                membermax = member.get("max")
                if not membermax:
                    raise ParseException("Missing max value in defNumber")
                memberstep = member.get("step")
                if not memberstep:
                    raise ParseException("Missing step value in defNumber")
                self.memberlabels[membername] = (label, memberformat, membermin, membermax, memberstep)
                if not member.text:
                    raise ParseException("Missing content in defNumber")
                self.data[membername] = member.text.strip()
            else:
                raise ParseException("Invalid tag in defNumberVector")
        if not self.data:
            raise ParseException("No member values in defNumberVector")


        # This method updates a property vector and sets it into the device 'data' dictionary
        # which is a dictionary of property name to propertyvector this device owns
        properties = device.data

        # does this vector already exist
        if self.vectorname in properties:
            self.vector = properties[self.vectorname]
            # set changed values into self.vector
            self.vector._defvector(self)
        else:
            # create a new NumberVector
            self.vector = propertyvectors.NumberVector(self)
            # add it to properties
            properties[self.vectorname] = self.vector



class defLightVector(defVector):

    """The remote driver has sent this to define a light vector property.
       This is a mapping of membername:value."""

    def __init__(self, root, device, client):
        defVector.__init__(self, root, device, client)
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defLight":
                membername = member.get("name")
                if not membername:
                    raise ParseException("No name given in defLight")
                label = member.get("label", membername)
                self.memberlabels[membername] = label
                if not member.text:
                    raise ParseException("No value given in defLight")
                value = member.text.strip()
                if not value in ('Idle','Ok','Busy','Alert'):
                    raise ParseException("Invalid value given in defLight")
                self.data[membername] = value
            else:
                raise ParseException("No members of defLight present")
        if not self.data:
            raise ParseException("No member values present")


        # This method updates a property vector and sets it into the device 'data' dictionary
        # which is a dictionary of property name to propertyvector this device owns
        properties = device.data

        # does this vector already exist
        if self.vectorname in properties:
            self.vector = properties[self.vectorname]
            # set changed values into self.vector by calling vector._defvector
            # with this event as its argument
            self.vector._defvector(self)
        else:
            # create a new LightVector
            self.vector = propertyvectors.LightVector(self)
            # add it to properties
            properties[self.vectorname] = self.vector



class defBLOBVector(defVector):

    """The remote driver has sent this to define a BLOB vector property.

       However this class does not have an object mapping of member name to value, since
       values are not given in defBLOBVectors"""


    def __init__(self, root, device, client):
        defVector.__init__(self, root, device, client)
        # self.data created by UserDict is not populated
        self.eventtype = "DefineBLOB"
        if self.devicename is None:
            raise ParseException("No device name given in defBLOBVector")
        self.perm = root.get("perm")
        if self.perm is None:
            raise ParseException("No perm given in defBLOBVector")
        if self.perm not in ('ro', 'wo', 'rw'):
            raise ParseException("Invalid perm given in defBLOBVector")
        try:
            timeout = root.get("timeout")
            if not self.timeout:
                self.timeout = 0.0
            else:
                self.timeout = float(timeout)
        except Exception:
            self.timeout = 0.0
        # create a dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defBLOB":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing member name in defBLOB")
                label = member.get("label", membername)
                self.memberlabels[membername] = label
            else:
                raise ParseException(f"Invalid child tag {member.tag} of defBLOBVector received")
        if not self.memberlabels:
            raise ParseException("No labels given in defBLOBVector")

        # properties is a dictionary of property name to propertyvector this device owns
        # This method updates a property vector and sets it into properties
        properties = device.data

        # does this vector already exist
        if self.vectorname in properties:
            self.vector = properties[self.vectorname]
            # set changed values into self.vector by calling vector._defvector
            # with this event as its argument
            self.vector._defvector(self)
        else:
            # create a new BLOBVector
            self.vector = propertyvectors.BLOBVector(self)
            # add it to properties
            properties[self.vectorname] = self.vector


class setVector(Event, UserDict):
    "Parent to set vectors, adds dictionary"
    def __init__(self, root, device, client):
        Event.__init__(self, root, device, client)
        UserDict.__init__(self)
        self.eventtype = "Set"
        if self.devicename is None:
            raise ParseException("Missing device name in set vector")
        self.vectorname = root.get("name")
        if self.vectorname is None:
            raise ParseException("Missing vector name in set vector")
        # This vector must already exist, and be enabled
        self.timeout = None
        if self.vectorname in self.device:
            vector = self.device[self.vectorname]
            if not vector.enable:
                raise ParseException("Set vector ignored as vector deleted")
        else:
            raise ParseException("Set vector ignored as vector is unknown")
        state = root.get("state")
        if state and (state in ('Idle','Ok','Busy','Alert')):
            self.state = state
        else:
            self.state = None
        self.message = root.get("message", "")

    def __setitem__(self, membername):
        raise KeyError



class setSwitchVector(setVector):
    """The remote driver is setting a Switch vector property.
       This is a mapping of membername:value."""

    def __init__(self, root, device, client):
        setVector.__init__(self, root, device, client)
        try:
            timeout = root.get("timeout")
            if not timeout is None:
                self.timeout = float(timeout)
        except Exception:
            # dont update
            pass
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneSwitch":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing name in oneSwitch")
                if not member.text:
                    raise ParseException("Missing value in oneSwitch")
                value = member.text.strip()
                if value == "On":
                    self.data[membername] = "On"
                elif value == "Off":
                    self.data[membername] = "Off"
                else:
                    raise ParseException("Invalid value in oneSwitch")
            else:
                raise ParseException("Invalid child tag of setSwitchVector")
        properties = device.data
        self.vector = properties[self.vectorname]
        # set changed values into self.vector
        self.vector._setvector(self)


class setTextVector(setVector):

    """The remote driver is setting a Text vector property.
       This is a mapping of membername:value."""

    def __init__(self, root, device, client):
        setVector.__init__(self, root, device, client)
        try:
            timeout = root.get("timeout")
            if not timeout is None:
                self.timeout = float(timeout)
        except Exception:
            # dont update
            pass
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneText":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing name in oneText")
                if not member.text:
                    value = ""
                else:
                    value = member.text.strip()
                self.data[membername] = value
            else:
                raise ParseException("Invalid child tag of setTextVector")
        properties = device.data
        self.vector = properties[self.vectorname]
        # set changed values into self.vector
        self.vector._setvector(self)


class setNumberVector(setVector):

    """The remote driver is setting a Number vector property.
       This is a mapping of membername:value.
       These number values are string values."""

    def __init__(self, root, device, client):
        setVector.__init__(self, root, device, client)
        try:
            timeout = root.get("timeout")
            if not timeout is None:
                self.timeout = float(timeout)
        except Exception:
            # dont update
            pass
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneNumber":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing name in oneNumber")
                if not member.text:
                    raise ParseException("Missing value in oneNumber")
                membervalue = member.text.strip()
                if not membervalue:
                    raise ParseException("Missing value in oneNumber")
                # test membervalue ok
                try:
                    memberfloat = getfloat(membervalue)
                except TypeError:
                    raise ParseException("Invalid number in setNumberVector")
                self.data[membername] = membervalue
            else:
                raise ParseException("Invalid child tag of setNumberVector")
        properties = device.data
        self.vector = properties[self.vectorname]
        # set changed values into self.vector
        self.vector._setvector(self)


class setLightVector(setVector):

    """The remote driver is setting a Light vector property.
       This is a mapping of membername:value.
       Note, the timeout attribute will always be None"""

    def __init__(self, root, device, client):
        setVector.__init__(self, root, device, client)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneLight":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing name in oneLight")
                if not member.text:
                    raise ParseException("Missing value in oneLight")
                value = member.text.strip()
                if not value in ('Idle','Ok','Busy','Alert'):
                    raise ParseException("Invalid value in oneLight")
                self.data[membername] = value
            else:
                raise ParseException("Invalid child tag of setLightVector")
        properties = device.data
        self.vector = properties[self.vectorname]
        # set changed values into self.vector
        self.vector._setvector(self)


class setBLOBVector(setVector):

    """The remote driver is setting a BLOB vector property.
       This is a mapping of membername:value, where value is a
       bytes object, taken from the received xml and b64 decoded
       This event has further attribute sizeformat being a dictionary
       of membername:(size, format) and which are then set into the target
       members as blobsize and blobformat attributes."""


    def __init__(self, root, device, client):
        setVector.__init__(self, root, device, client)
        self.eventtype = "SetBLOB"
        try:
            timeout = root.get("timeout")
            if not timeout is None:
                self.timeout = float(timeout)
        except Exception:
            # dont update
            pass
        # create a dictionary of member name to value
        # and dictionary sizeformat
        # with key member name and value being a tuple of size, format
        self.sizeformat = {}
        for member in root:
            if member.tag == "oneBLOB":
                membername = member.get("name")
                if not membername:
                    raise ParseException("Missing name in oneBLOB")
                membersize = member.get("size")
                if not membersize:
                    raise ParseException("Missing size in oneBLOB")
                try:
                    memberize = int(membersize)
                except Exception:
                    raise ParseException("Invalid size in oneBLOB")
                memberformat = member.get("format")
                if not memberformat:
                    raise ParseException("Missing format in oneBLOB")
                if not member.text:
                    raise ParseException("Missing value in oneBLOB")
                try:
                    self.data[membername] = standard_b64decode(member.text.encode('ascii'))
                except Exception:
                    raise ParseException("Unable to decode oneBLOB contents")
                self.sizeformat[membername] = (membersize, memberformat)
            else:
                raise ParseException("Invalid child tag of setBLOBVector")
        self.vector = device[self.vectorname]
        # set changed values into self.vector
        self.vector._setvector(self)
