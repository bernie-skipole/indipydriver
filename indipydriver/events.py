

from datetime import datetime


from base64 import standard_b64decode

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


class newSwitchVector(Event):
    "defines an event with self._values, and self.timestamp"

    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname, vector, root)
        timestamp_string = root.get("timestamp")
        if timestamp_string:
            try:
                self.timestamp = datetime.fromisoformat(timestamp_string)
            except:
                raise EventException
        else:
            self.timestamp = datetime.utcnow()
        # create a dictionary of member name to value
        self._values = {}
        for member in root:
            if member.tag == "oneSwitch":
                membername = member.get("name")
                if membername in self.vector:
                    value = member.text
                    if value == "On":
                        self._values[membername] = "On"
                    elif value == "Off":
                        self._values[membername] = "Off"
                    else:
                        raise EventException
                else:
                    raise EventException
            else:
                raise EventException
        if not self._values:
            raise EventException

    def __getitem__(self, membername):
        return self._values[membername]

    def __contains__(self, membername):
        return membername in self._values

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._values.keys()

    def items(self):
        return self._values.items()

    def values(self):
        return self._values.values()



class newTextVector(Event):
    "defines an event with self._values, and self.timestamp"

    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname, vector, root)
        timestamp_string = root.get("timestamp")
        if timestamp_string:
            try:
                self.timestamp = datetime.fromisoformat(timestamp_string)
            except:
                raise EventException
        else:
            self.timestamp = datetime.utcnow()
        # create a dictionary of member name to value
        self._values = {}
        for member in root:
            if member.tag == "oneText":
                membername = member.get("name")
                if membername in self.vector:
                    self._values[membername] = member.text
                else:
                    raise EventException
            else:
                raise EventException
        if not self._values:
            raise EventException

    def __getitem__(self, membername):
        return self._values[membername]

    def __contains__(self, membername):
        return membername in self._values

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._values.keys()

    def items(self):
        return self._values.items()

    def values(self):
        return self._values.values()



class newNumberVector(Event):
    "defines an event with self._values, and self.timestamp"

    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname, vector, root)
        timestamp_string = root.get("timestamp")
        if timestamp_string:
            try:
                self.timestamp = datetime.fromisoformat(timestamp_string)
            except:
                raise EventException
        else:
            self.timestamp = datetime.utcnow()
        # create a dictionary of member name to value
        self._values = {}
        self.floatvalues = {}
        for member in root:
            if member.tag == "oneNumber":
                membername = member.get("name")
                if membername in self.vector:
                    self._values[membername] = member.text
                else:
                    raise EventException
            else:
                raise EventException
        if not self._values:
            raise EventException

    def __getitem__(self, membername):
        return self._values[membername]

    def __contains__(self, membername):
        return membername in self._values

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._values.keys()

    def items(self):
        return self._values.items()

    def values(self):
        return self._values.values()



class newBLOBVector(Event):
    """defines an event with self._values, self.sizeformat and self.timestamp
       The values of the self.sizeformat dictionary is a tuple of filesize, fileformat"""

    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname, vector, root)
        timestamp_string = root.get("timestamp")
        if timestamp_string:
            try:
                self.timestamp = datetime.fromisoformat(timestamp_string)
            except:
                raise EventException
        else:
            self.timestamp = datetime.utcnow()
        # create a dictionary of member name to value
        self._values = {}
        self.sizeformat = {}
        for member in root:
            if member.tag == "oneBLOB":
                membername = member.get("name")
                if membername in self.vector:
                    try:
                        self._values[membername] = standard_b64decode(member.text.encode('ascii'))
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
        if not self._values:
            raise EventException

    def __getitem__(self, membername):
        return self._values[membername]

    def __contains__(self, membername):
        return membername in self._values

    def __iter__(self):
        return iter(self._values)

    def keys(self):
        return self._values.keys()

    def items(self):
        return self._values.items()

    def values(self):
        return self._values.values()
