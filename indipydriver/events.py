

from datetime import datetime

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


class newSwitchVector(Event):
    "defines an event with self.values, and self.timestamp"

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
        self.values = {}
        for member in root:
            if member.tag == "oneSwitch":
                membername = member.get("name")
                if membername in self.vector:
                    value = member.text
                    if value == "On":
                        self.values[membername] = "On"
                    elif value == "Off":
                        self.values[membername] = "Off"
                    else:
                        raise EventException
                else:
                    raise EventException
            else:
                raise EventException
        if not self.values:
            raise EventException


class newTextVector(Event):
    "defines an event with self.values, and self.timestamp"

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
        self.values = {}
        for member in root:
            if member.tag == "oneText":
                membername = member.get("name")
                if membername in self.vector:
                    self.values[membername] = member.text
                else:
                    raise EventException
            else:
                raise EventException
        if not self.values:
            raise EventException
