

from datetime import datetime

class Event:

    def __init__(self, devicename, vectorname):
        self.devicename = devicename
        self.vectorname = vectorname


class EventException(Exception):
    "Raised if an error occurs when parsing received data"
    pass



class getProperties(Event):

    def __init__(self, devicename, vectorname, vector):
        super().__init__(devicename, vectorname)
        self.vector = vector

    def send(self, timestamp=None, timeout=0, message=''):
        if not timestamp:
            timestamp = datetime.utcnow()
        self.vector.send_defVector(timestamp, timeout, message)


class newSwitchVector(Event):

    "defines an event with self.values, and self.timestamp"

    def __init__(self, devicename, vectorname, vector, root):
        super().__init__(devicename, vectorname)
        self.vector = vector
        timestamp_string = root.get(timestamp)       ##### convert to datetime object
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
