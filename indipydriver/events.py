

from datetime import datetime

class Event:

    def __init__(self, devicename, vectorname):
        self.devicename = devicename
        self.vectorname = vectorname



class getProperties(Event):

    def __init__(self, devicename, vectorname, vector):
        super().__init__(devicename, vectorname)
        self.vector = vector

    def send(self, timestamp=None, timeout=0, message=''):
        if not timestamp:
            timestamp = datetime.utcnow()
        self.vector.send_defVector(timestamp, timeout, message)
