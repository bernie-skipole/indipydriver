

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


class newSwitchVector(Event, UserDict):
    "defines an event with self.timestamp"

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

    def __setitem__(self, membername):
        raise KeyError


class newTextVector(Event, UserDict):
    "defines an event with self.timestamp"

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

    def __setitem__(self, membername):
        raise KeyError



class newNumberVector(Event, UserDict):
    "defines an event with self.timestamp"

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

    def __setitem__(self, membername):
        raise KeyError



class newBLOBVector(Event, UserDict):
    """defines an event with self._values, self.sizeformat and self.timestamp
       The values of the self.sizeformat dictionary is a tuple of filesize, fileformat"""

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
        # create a dictionary of member name to value
        self.sizeformat = {}
        for member in root:
            if member.tag == "oneBLOB":
                membername = member.get("name")
                if membername in self.vector:
                    try:
                        self.data[membername] = standard_b64decode(member.text.encode('ascii'))
                        filesize = int(member.get("size"))
                    except:
                        raise EventException
                    fileformat = member.get("format")
                    if not fileformat:
                        raise EventException
                    self.sizeformat[membername] = (filesize, fileformat)
                else:
                    raise EventException
            else:
                raise EventException
        if not self.data:
            raise EventException

    def __setitem__(self, membername):
        raise KeyError
