

from datetime import datetime

from base64 import standard_b64decode

from collections import UserDict

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
    "defines an event with self.value one of Never, Also, Only"

    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname, vector, root)
        value = root.text
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
        if timestamp_string:
            try:
                self.timestamp = datetime.fromisoformat(timestamp_string)
            except:
                raise EventException
        else:
            self.timestamp = datetime.utcnow()

    def __setitem__(self, membername):
        raise KeyError


class newSwitchVector(newVector):

    def __init__(self, devicename, vectorname, vector, root):
        newVector.__init__(self, devicename, vectorname, vector, root)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneSwitch":
                membername = member.get("name")
                if membername in self.vector:
                    value = member.text
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

    def __init__(self, devicename, vectorname, vector, root):
        newVector.__init__(self, devicename, vectorname, vector, root)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneNumber":
                membername = member.get("name")
                if membername in self.vector:
                    self.data[membername] = member.text
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException


class newBLOBVector(newVector):

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
        if timestamp_string:
            try:
                self.timestamp = datetime.fromisoformat(timestamp_string)
            except:
                raise EventException
        else:
            self.timestamp = datetime.utcnow()


class Message(SnoopEvent):

    def __init__(self, root):
        super().__init__(root)
        self.message = root.get("message", "")


class delProperty(SnoopEvent):

    def __init__(self, root):
        super().__init__(root)
        if self.devicename is None:
            raise EventException
        self.vectorname = root.get("name")
        self.message = root.get("message", "")


class defVector(SnoopEvent, UserDict):
    "Parent to def vectors, adds dictionary"
    def __init__(self, root):
        SnoopEvent.__init__(self, root)
        UserDict.__init__(self)
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

    def __setitem__(self, membername):
        raise KeyError


class defSwitchVector(defVector):

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
                value = member.text
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
                self.data[membername] = member.text
            else:
                raise EventException
        if not self.data:
            raise EventException


class defLightVector(defVector):

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
                value = member.text
                if not value in ('Idle','Ok','Busy','Alert'):
                    raise EventException
                self.data[membername] = value
            else:
                raise EventException
        if not self.data:
            raise EventException


class defBLOBVector(SnoopEvent):

    "This does not have an object mapping of member name to value, since values are not given in defBLOBVectors"

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

    def __init__(self, root):
        setVector.__init__(self, root)
        self.timeout = root.get("timeout", "0")
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneSwitch":
                membername = member.get("name")
                if not membername:
                    raise EventException
                value = member.text
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

    def __init__(self, root):
        setVector.__init__(self, root)
        self.timeout = root.get("timeout", "0")
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneNumber":
                membername = member.get("name")
                if not membername:
                    raise EventException
                self.data[membername] = member.text
            else:
                raise EventException
        if not self.data:
            raise EventException

class setLightVector(setVector):

    def __init__(self, root):
        setVector.__init__(self, root)
        # create a dictionary of member name to value
        for member in root:
            if member.tag == "oneLight":
                membername = member.get("name")
                if not membername:
                    raise EventException
                value = member.text
                if not value in ('Idle','Ok','Busy','Alert'):
                    raise EventException
                self.data[membername] = value
            else:
                raise EventException
        if not self.data:
            raise EventException


class setBLOBVector(setVector):

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
