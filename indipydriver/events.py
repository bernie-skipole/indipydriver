
import sys

from datetime import datetime, timezone

from base64 import standard_b64decode

from collections import UserDict


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
        except:
            timestamp = None
    else:
        timestamp = datetime.now(tz=timezone.utc)
    return timestamp


class Event:
    "Parent class for events"
    def __init__(self, devicename, vectorname, vector, root):
        self.devicename = devicename
        self.vectorname = vectorname
        self.vector = vector
        self.root = root


class EventException(Exception):
    "Raised if an error occurs when parsing received data"
    pass


class getProperties(Event):
    "defines an event that a getProperties has been received"
    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname, vector, root)



class enableBLOB(Event):
    """Defines an event with self.value being one of Never, Also,
       or Only. This can be ignored by the driver. It is automatically
       acted on."""

    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname, vector, root)
        value = root.text.strip()
        if value in ("Never", "Also", "Only"):
            self.value = value
        else:
            # unrecognised value
            raise EventException


class newVector(Event, UserDict):
    "Parent to new vectors, adds dictionary and self.timestamp"
    def __init__(self, devicename, vectorname, vector, root):
        Event.__init__(self, devicename, vectorname, vector, root)
        UserDict.__init__(self)
        timestamp_string = root.get("timestamp")
        self.timestamp = _parse_timestamp(timestamp_string)

    def __setitem__(self, membername):
        raise KeyError


class newSwitchVector(newVector):
    """An event indicating a newSwitchVector has been received, this is a mapping
       of membername:value, where each value is either On or Off"""

    def __init__(self, devicename, vectorname, vector, root):
        newVector.__init__(self, devicename, vectorname, vector, root)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneSwitch":
                membername = member.get("name")
                if membername in self.vector:
                    value = member.text.strip()
                    if value == "On":
                        self.data[membername] = "On"
                    elif value == "Off":
                        self.data[membername] = "Off"
                    else:
                        raise EventException
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException

class newTextVector(newVector):
    """An event indicating a newTextVector has been received, this is a mapping
       of membername:value, where each value is a text string"""


    def __init__(self, devicename, vectorname, vector, root):
        newVector.__init__(self, devicename, vectorname, vector, root)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneText":
                membername = member.get("name")
                if membername in self.vector:
                    self.data[membername] = member.text
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException


class newNumberVector(newVector):
    """An event indicating a newNumberVector has been received, this is a mapping
       of membername:value, where each value is a string number, which may be in
       sexagesimal format, and may have newlines appended or prepended. If desired,
       the driver method indi_number_to_float() can be used to convert this to a float."""

    def __init__(self, devicename, vectorname, vector, root):
        newVector.__init__(self, devicename, vectorname, vector, root)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneNumber":
                membername = member.get("name")
                if membername in self.vector:
                    self.data[membername] = member.text.strip()
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException


class newBLOBVector(newVector):
    """An event indicating a newBLOBVector has been received, this is a mapping
       of membername:value, where each value is a bytes string.

       This contains a further attribute 'sizeformat' which is a dictionary
       of membername:(membersize, memberformat) these values are provided by the
       client."""

    def __init__(self, devicename, vectorname, vector, root):
        newVector.__init__(self, devicename, vectorname, vector, root)
        # create a dictionary of member name to value,
        # and dictionary sizeformat
        # with key member name and value being a tuple of size, format
        self.sizeformat = {}
        for member in root:
            if member.tag == "oneBLOB":
                membername = member.get("name")
                if membername in self.vector:
                    try:
                        self.data[membername] = standard_b64decode(member.text.encode('ascii'))
                        membersize = int(member.get("size"))
                    except:
                        raise EventException
                    memberformat = member.get("format")
                    if not memberformat:
                        raise EventException
                    self.sizeformat[membername] = (membersize, memberformat)
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException


class SnoopEvent:
    "Parent class for snoop events"
    def __init__(self, root):
        self.devicename = root.get("device")
        self.root = root
        timestamp_string = root.get("timestamp")
        self.timestamp = _parse_timestamp(timestamp_string)


class Message(SnoopEvent):
    """This contains attribute 'message' with the message string sent by the remote driver.
       Attribute devicename could be None if the driver is sending a system wide message."""

    def __init__(self, root):
        super().__init__(root)
        self.message = root.get("message", "")


class delProperty(SnoopEvent):
    """The remote driver is instructing the client to delete either a device or a vector property.
       This contains attribute vectorname, if it is None, then the whole device is to be deleted.
       A 'message' attribute contains any message sent by the client with this instruction."""

    def __init__(self, root):
        super().__init__(root)
        if self.devicename is None:
            raise EventException
        self.vectorname = root.get("name")
        self.message = root.get("message", "")


class defVector(SnoopEvent, UserDict):
    "Parent to def vectors, adds a mapping of membername:value"
    def __init__(self, root):
        SnoopEvent.__init__(self, root)
        UserDict.__init__(self)
        self.vectorname = root.get("name")
        if self.vectorname is None:
            raise EventException
        self.label = root.get("label", self.vectorname)
        self.group = root.get("group", "")
        state = root.get("state")
        if not state:
            raise EventException
        if not state in ('Idle','Ok','Busy','Alert'):
            raise EventException
        self.state = state
        self.message = root.get("message", "")

    def __setitem__(self, membername):
        raise KeyError


class defSwitchVector(defVector):

    """The remote driver has sent this to define a switch vector property, it has further
       attributes perm, rule, timeout, and memberlabels which is a dictionary of
       membername:label."""

    def __init__(self, root):
        defVector.__init__(self, root)
        self.perm = root.get("perm")
        if self.perm is None:
            raise EventException
        if self.perm not in ('ro', 'wo', 'rw'):
            raise EventException
        self.rule = root.get("rule")
        if self.rule is None:
            raise EventException
        if self.rule not in ('OneOfMany', 'AtMostOne', 'AnyOfMany'):
            raise EventException
        self.timeout = root.get("timeout", "0")
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defSwitch":
                membername = member.get("name")
                if not membername:
                    raise EventException
                label = member.get("label", membername)
                self.memberlabels[membername] = label
                value = member.text.strip()
                if value == "On":
                    self.data[membername] = "On"
                elif value == "Off":
                    self.data[membername] = "Off"
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException


class defTextVector(defVector):

    """The remote driver has sent this to define a text vector property, it has further
       attributes perm, timeout, and memberlabels which is a dictionary of
       membername:label."""

    def __init__(self, root):
        defVector.__init__(self, root)
        self.perm = root.get("perm")
        if self.perm is None:
            raise EventException
        if self.perm not in ('ro', 'wo', 'rw'):
            raise EventException
        self.timeout = root.get("timeout", "0")
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defText":
                membername = member.get("name")
                if not membername:
                    raise EventException
                label = member.get("label", membername)
                self.memberlabels[membername] = label
                self.data[membername] = member.text
            else:
                raise EventException
        if not self.data:
            raise EventException


class defNumberVector(defVector):

    """The remote driver has sent this to define a number vector property, it has further
       attributes perm, timeout, and memberlabels which is a dictionary of
       membername:(label, format, min, max, step)."""

    def __init__(self, root):
        defVector.__init__(self, root)
        self.perm = root.get("perm")
        if self.perm is None:
            raise EventException
        if self.perm not in ('ro', 'wo', 'rw'):
            raise EventException
        self.timeout = root.get("timeout", "0")
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and
        # value being a tuple of (label, format, min, max, step)
        self.memberlabels = {}
        for member in root:
            if member.tag == "defNumber":
                membername = member.get("name")
                if not membername:
                    raise EventException
                label = member.get("label", membername)
                memberformat = member.get("format")
                if not memberformat:
                    raise EventException
                membermin = member.get("min")
                if not membermin:
                    raise EventException
                membermax = member.get("max")
                if not membermax:
                    raise EventException
                memberstep = member.get("step")
                if not memberstep:
                    raise EventException
                self.memberlabels[membername] = (label, memberformat, membermin, membermax, memberstep)
                self.data[membername] = member.text.strip()
            else:
                raise EventException
        if not self.data:
            raise EventException


class defLightVector(defVector):

    """The remote driver has sent this to define a light vector property, it has further
       attribute memberlabels which is a dictionary of membername:label."""

    def __init__(self, root):
        defVector.__init__(self, root)
        # create object dictionary of member name to value
        # and another dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defLight":
                membername = member.get("name")
                if not membername:
                    raise EventException
                label = member.get("label", membername)
                self.memberlabels[membername] = label
                value = member.text.strip()
                if not value in ('Idle','Ok','Busy','Alert'):
                    raise EventException
                self.data[membername] = value
            else:
                raise EventException
        if not self.data:
            raise EventException


class defBLOBVector(SnoopEvent):

    """The remote driver has sent this to define a BLOB vector property, it has further
       attributes perm, timeout, and memberlabels which is a dictionary of
       membername:label.

       However this class does not have an object mapping of member name to value, since
       values are not given in defBLOBVectors"""

    def __init__(self, root):
        SnoopEvent.__init__(self, root)
        if self.devicename is None:
            raise EventException
        self.vectorname = root.get("name")
        if self.vectorname is None:
            raise EventException
        self.label = root.get("label", self.vectorname)
        self.group = root.get("group", "")
        state = root.get("state")
        if not state:
            raise EventException
        if not state in ('Idle','Ok','Busy','Alert'):
            raise EventException
        self.state = state
        self.message = root.get("message", "")
        self.perm = root.get("perm")
        if self.perm is None:
            raise EventException
        if self.perm not in ('ro', 'wo', 'rw'):
            raise EventException
        self.timeout = root.get("timeout", "0")
        # create a dictionary of self.memberlabels with key member name and value being label
        self.memberlabels = {}
        for member in root:
            if member.tag == "defBLOB":
                membername = member.get("name")
                if not membername:
                    raise EventException
                label = member.get("label", membername)
                self.memberlabels[membername] = label
            else:
                raise EventException
        if not self.memberlabels:
            raise EventException


class setVector(SnoopEvent, UserDict):
    "Parent to set vectors, adds dictionary"
    def __init__(self, root):
        SnoopEvent.__init__(self, root)
        UserDict.__init__(self)
        if self.devicename is None:
            raise EventException
        self.vectorname = root.get("name")
        if self.vectorname is None:
            raise EventException
        state = root.get("state")
        if state and (state in ('Idle','Ok','Busy','Alert')):
            self.state = state
        else:
            self.state = None
        self.message = root.get("message", "")

    def __setitem__(self, membername):
        raise KeyError


class setSwitchVector(setVector):
    """The remote driver is setting a Switch vector property, this
       has further attribute timeout."""

    def __init__(self, root):
        setVector.__init__(self, root)
        self.timeout = root.get("timeout", "0")
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneSwitch":
                membername = member.get("name")
                if not membername:
                    raise EventException
                value = member.text.strip()
                if value == "On":
                    self.data[membername] = "On"
                elif value == "Off":
                    self.data[membername] = "Off"
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException


class setTextVector(setVector):

    """The remote driver is setting a Text vector property, this
       has further attribute timeout."""

    def __init__(self, root):
        setVector.__init__(self, root)
        self.timeout = root.get("timeout", "0")
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneText":
                membername = member.get("name")
                if not membername:
                    raise EventException
                self.data[membername] = member.text
            else:
                raise EventException
        if not self.data:
            raise EventException


class setNumberVector(setVector):

    """The remote driver is setting a Number vector property, this
       has further attribute timeout. The number values of the
       membername:membervalue are string values."""

    def __init__(self, root):
        setVector.__init__(self, root)
        self.timeout = root.get("timeout", "0")
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneNumber":
                membername = member.get("name")
                if not membername:
                    raise EventException
                self.data[membername] = member.text.strip()
            else:
                raise EventException
        if not self.data:
            raise EventException

class setLightVector(setVector):

    """The remote driver is setting a Light vector property."""

    def __init__(self, root):
        setVector.__init__(self, root)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneLight":
                membername = member.get("name")
                if not membername:
                    raise EventException
                value = member.text.strip()
                if not value in ('Idle','Ok','Busy','Alert'):
                    raise EventException
                self.data[membername] = value
            else:
                raise EventException
        if not self.data:
            raise EventException


class setBLOBVector(setVector):

    """The remote driver is setting a BLOB vector property, this
       has further attributes timeout and sizeformat which is a dictionary
       of membername:(size, format)."""

    def __init__(self, root):
        setVector.__init__(self, root)
        self.timeout = root.get("timeout", "0")
        # create a dictionary of member name to value
        # and dictionary sizeformat
        # with key member name and value being a tuple of size, format
        self.sizeformat = {}
        for member in root:
            if member.tag == "oneBLOB":
                membername = member.get("name")
                if not membername:
                    raise EventException
                membersize = member.get("size")
                if not membersize:
                    raise EventException
                memberformat = member.get("format")
                if not memberformat:
                    raise EventException
                try:
                    self.data[membername] = standard_b64decode(member.text.encode('ascii'))
                    memberize = int(member.get("size"))
                except:
                    raise EventException
                self.sizeformat[membername] = (membersize, memberformat)
            else:
                raise EventException
        if not self.data:
            raise EventException
