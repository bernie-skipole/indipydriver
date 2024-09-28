
import collections, sys, time, json

from datetime import datetime, timezone

import asyncio

import xml.etree.ElementTree as ET

from .propertymembers import SwitchMember, LightMember, TextMember, NumberMember, BLOBMember, ParseException


class Vector(collections.UserDict):

    """This class is the parent of the PropertyVector class, which in turn
       is the parent of SwitchVector, LightVector, TextVector, NumberVector
       and BLOBVector classes.
       It is a mapping of membername to member value.
       """

    def __init__(self, name, label, group, state, timestamp, message):
        super().__init__()

        # UserDict will create self.data which will be a dictionary of
        # member name to member this vector owns

        self.name = name
        self.label = label
        self.group = group
        self._state = state
        self.timestamp = timestamp
        self.message = message
        self.vectortype = self.__class__.__name__
        self.devicename = None
        self._rule = None
        self._perm = None
        self.timeout = 0.0
        # if self.enable is False, this property is 'deleted'
        self.enable = True


    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        if not value in ('Idle','Ok','Busy','Alert'):
            raise ValueError("Invalid state given")
        self._state = value

    @property
    def rule(self):
        return self._rule

    @rule.setter
    def rule(self, value):
        if value not in ('OneOfMany', 'AtMostOne', 'AnyOfMany'):
            raise ValueError("Invalid rule given")
        self._rule = value

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        if value not in ('ro', 'wo', 'rw'):
            raise ValueError("Invalid permission given")
        self._perm = value

    def __setitem__(self, membername, value):
        self.data[membername].membervalue = value

    def __getitem__(self, membername):
        return self.data[membername].membervalue

    def members(self):
        "Returns a dictionary of member objects"
        return self.data

    def memberlabel(self, membername):
        "Returns the member label, given a member name"
        return self.data[membername].label


class SnapVector(Vector):
    """This object is used as a snapshot of this vector.
       Should you use the ipyclient.snapshot method to create a snapshot,
       the snapshot device will contain objects of this vector class. Which
       does not have the methods of SwitchVector, etc..
       This allows the snapshot to be read without risk of creating any
       side effects."""

    def dictdump(self):
        "Returns a dictionary of this vector"
        vecdict = {}
        memdict = {}
        for membername, member in self.data.items():
            memdict[membername] = member.dictdump()
        vecdict = {"vectortype":self.vectortype,
                   "name":self.name,
                   "devicename":self.devicename,
                   "label":self.label,
                   "message":self.message,
                   "enable":self.enable,
                   "group":self.group,
                   "state":self.state,
                   "timeout":self.timeout,
                   "timestamp":self.timestamp.isoformat(sep='T')}
        if self.rule:
            vecdict["rule"] = self.rule
        if self.perm:
            vecdict["perm"] = self.perm

        vecdict["members"] = memdict
        return vecdict

    def dumps(self, indent=None, separators=None):
        "Returns a JSON string of the snapshot."
        return json.dumps(self.dictdump(), indent=indent, separators=separators)


    def dump(self, fp, indent=None, separators=None):
        """Serialize the snapshot as a JSON formatted stream to fp, a file-like object.
           This uses the Python json module which always produces str objects, not bytes
           objects. Therefore, fp.write() must support str input."""
        return json.dump(self.dictdump(), fp, indent=indent, separators=separators)




class PropertyVector(Vector):
    "Inherits from Vector, and is the parent class of SwitchVector etc.."

    def __init__(self, name, label, group, state, timestamp, message, device, client):
        super().__init__(name, label, group, state, timestamp, message)
        self._client = client
        self.device = device
        self.devicename = device.devicename

        self._timer = False   # Set true when a timer is going after a newvector is sent
                              # set False when a setvector is received
        self._newtimer = 0    # Set to time.time() when a new vector is sent


    def checktimedout(self, nowtime):
        "Returns True if a timedout has occured, False otherwise"

        if not self._client.timeout_enable:
            self._timer = False
        if not self._timer:
            return False
        # so timer is running
        if self.timeout > self._client.vector_timeout_max:
            t = self._client.vector_timeout_max
        elif self.timeout < self._client.vector_timeout_min:
            t = self._client.vector_timeout_min
        else:
            t = self.timeout
        if nowtime > self._newtimer + t:
            # timed out
            self._timer = False
            return True
        return False

    def checkvalue(self, value, allowed):
        "allowed is a list of values, checks if value is in it"
        if value not in allowed:
            raise ParseException(f"Invalid value:{value}")
        return value

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = self.checkvalue(value, ['Idle','Ok','Busy','Alert'])


    def __setitem__(self, membername, value):
        "Members are added by being learnt from the driver, they cannot be manually added"
        raise KeyError

    def __getitem__(self, membername):
        return self.data[membername].membervalue

    def _setvector(self, event):
        "Updates this vector with new values after a set... vector has been received"
        if not self.enable:
            # this property does not exist
            return
        if event.state:
            self.state = event.state
        if event.timestamp:
            self.timestamp = event.timestamp
        if event.message:
            self.message = event.message
        if hasattr(event, 'timeout'):
            if not self.timeout is None:
                self.timeout = event.timeout
        for membername, membervalue in event.items():
            if membername in self.data:
                member = self.data[membername]
                member.membervalue = membervalue
        # turn off timer if all updates are successful
        self._timer = False


    def snapshot(self):
        """Take a snapshot of the vector and returns an object which is a restricted copy
           of the current state of the vector.
           Vector methods for sending data will not be available.
           This copy will not be updated by events. This is provided so that you can
           handle the vector data, without fear of the value changing."""
        snapvector = SnapVector(self.name, self.label, self.group, self.state, self.timestamp, self.message)
        snapvector.vectortype = self.vectortype
        snapvector.devicename = self.devicename
        snapvector.enable = self.enable
        if hasattr(self, 'rule') and self.rule:
            snapvector.rule = self.rule
        if hasattr(self, 'perm') and self.perm:
            snapvector.perm = self.perm
        if hasattr(self, 'timeout') and self.timeout:
            snapvector.timeout = self.timeout
        for membername, member in self.data.items():
            snapvector.data[membername] = member._snapshot()
        return snapvector



class SwitchVector(PropertyVector):

    """A SwitchVector sends and receives one or more members with values 'On' or 'Off'. It
       also has the extra attribute 'rule' which can be one of 'OneOfMany', 'AtMostOne', 'AnyOfMany'.
       These are hints to the client how to display the switches in the vector.

       OneOfMany - of the SwitchMembers in this vector, one (and only one) must be On.

       AtMostOne - of the SwitchMembers in this vector, one or none can be On.

       AnyOfMany - multiple switch members can be On.
       """

    def __init__(self, event):
        super().__init__(event.vectorname, event.label, event.group, event.state,
                         event.timestamp, event.message, event.device, event._client)
        self._perm = event.perm
        self._rule = event.rule
        self.timeout = event.timeout
        # self.data is a dictionary of switch name : switchmember
        # create  members
        for membername, membervalue in event.items():
            self.data[membername] = SwitchMember(membername, event.memberlabels[membername], membervalue)

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    @property
    def rule(self):
        return self._rule

    @rule.setter
    def rule(self, value):
        self._rule = self.checkvalue(value, ['OneOfMany','AtMostOne','AnyOfMany'])


    def _defvector(self, event):
        "Updates this vector with new values after a def... vector has been received"
        self._timer = False
        if event.label:
            self.label = event.label
        if event.group:
            self.group = event.group
        if event.perm:
            self.perm = event.perm
        if event.rule:
            self.rule = event.rule
        if event.state:
            self.state = event.state
        if event.timestamp:
            self.timestamp = event.timestamp
        if event.message:
            self.message = event.message
        self.timeout = event.timeout
        # create  members
        for membername, membervalue in event.items():
            if membername in self.data:
                # update existing member
                if event.memberlabels[membername]:
                    self.data[membername].label = event.memberlabels[membername]
                self.data[membername].membervalue = membervalue
            else:
                # create new member
                self.data[membername] = SwitchMember(membername, event.memberlabels[membername], membervalue)
        self.enable = True

    def _newSwitchVector(self, timestamp=None, members={}):
        "Creates the xmldata for sending a newSwitchVector"
        if not self.enable:
            return
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        if not isinstance(timestamp, datetime):
            # invalid timestamp given
            return
        if not (timestamp.tzinfo is None):
            if timestamp.tzinfo == timezone.utc:
                timestamp = timestamp.replace(tzinfo = None)
            else:
                # invalid timestamp
                return
        # timestamp has no tzinfo so isoformat does not include timezone info
        self.state = 'Busy'
        xmldata = ET.Element('newSwitchVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("timestamp", timestamp.isoformat(sep='T'))
        # set member values to send
        sendvalues = {}
        for membername, value in members.items():
            # check this membername exists
            if membername in self:
                sendvalues[membername] = value
        # for rule 'OneOfMany' the standard indicates 'Off' should precede 'On'
        # so make all 'On' values last
        Offswitches = []
        Onswitches = []
        for mname, value in sendvalues.items():
            if value == 'Off':
                # create list of (memberswitch, new value) tuples
                Offswitches.append( ( self.data[mname], value ) )
            elif value == 'On':
               Onswitches.append( ( self.data[mname], value ) )
        for switch,value in Offswitches:
            xmldata.append(switch.oneswitch(value))
        for switch, value in Onswitches:
            xmldata.append(switch.oneswitch(value))
        return xmldata


    async def send_newSwitchVector(self, timestamp=None, members={}):
        """Transmits the vector (newSwitchVector) and the members given in the members
           dictionary which consists of member names:values to be sent.
           The values should be strings of either On or Off.
           This method will encode and transmit the xml, and change the vector state to busy.
           If no timestamp is given, a current UTC time will be created."""
        xmldata = self._newSwitchVector(timestamp, members)
        if xmldata is None:
            return
        self._timer = True
        self._newtimer = time.time()
        await self._client.send(xmldata)


class LightVector(PropertyVector):

    """A LightVector is an instrument indicator, and has one or more members
       with values 'Idle', 'Ok', 'Busy' or 'Alert'. In general a client will
       indicate this state with different colours.

       This class has no 'send_newLightVector method, since lights are read-only"""

    def __init__(self, event):
        super().__init__(event.vectorname, event.label, event.group, event.state,
                         event.timestamp, event.message, event.device, event._client)
        self._perm = "ro"
        # self.data is a dictionary of light name : lightmember
        # create  members
        for membername, membervalue in event.items():
            self.data[membername] = LightMember(membername, event.memberlabels[membername], membervalue)

    @property
    def perm(self):
        return "ro"

    @perm.setter
    def perm(self, value):
        pass

    def checktimedout(self, nowtime):
        "As ro, always returns False"
        return False

    def _defvector(self, event):
        "Updates this vector with new values after a def... vector has been received"
        if event.label:
            self.label = event.label
        if event.group:
            self.group = event.group
        if event.state:
            self.state = event.state
        if event.timestamp:
            self.timestamp = event.timestamp
        if event.message:
            self.message = event.message
        # create  members
        for membername, membervalue in event.items():
            if membername in self.data:
                # update existing member
                if event.memberlabels[membername]:
                    self.data[membername].label = event.memberlabels[membername]
                self.data[membername].membervalue = membervalue
            else:
                # create new member
                self.data[membername] = LightMember(membername, event.memberlabels[membername], membervalue)
        self.enable = True

    def snapshot(self):
        snapvector = PropertyVector.snapshot(self)
        snapvector.perm = "ro"
        return snapvector



class TextVector(PropertyVector):

    """A TextVector is used to send and receive text between instrument and client."""


    def __init__(self, event):
        super().__init__(event.vectorname, event.label, event.group, event.state,
                         event.timestamp, event.message, event.device, event._client)
        self._perm = event.perm
        self.timeout = event.timeout
        # self.data is a dictionary of text name : textmember
        # create  members
        for membername, membervalue in event.items():
            self.data[membername] = TextMember(membername, event.memberlabels[membername], membervalue)

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    def _defvector(self, event):
        "Updates this vector with new values after a def... vector has been received"
        self._timer = False
        if event.label:
            self.label = event.label
        if event.group:
            self.group = event.group
        if event.perm:
            self.perm = event.perm
        if event.state:
            self.state = event.state
        if event.timestamp:
            self.timestamp = event.timestamp
        if event.message:
            self.message = event.message
        self.timeout = event.timeout
        # create  members
        for membername, membervalue in event.items():
            if membername in self.data:
                # update existing member
                if event.memberlabels[membername]:
                    self.data[membername].label = event.memberlabels[membername]
                self.data[membername].membervalue = membervalue
            else:
                # create new member
                self.data[membername] = TextMember(membername, event.memberlabels[membername], membervalue)
        self.enable = True


    def _newTextVector(self, timestamp=None, members={}):
        "Creates the xmldata for sending a newTextVector"
        if not self.enable:
            return
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        if not isinstance(timestamp, datetime):
            # invalid timestamp given
            return
        if not (timestamp.tzinfo is None):
            if timestamp.tzinfo == timezone.utc:
                timestamp = timestamp.replace(tzinfo = None)
            else:
                # invalid timestamp
                return
        # timestamp has no tzinfo so isoformat does not include timezone info
        self.state = 'Busy'
        xmldata = ET.Element('newTextVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("timestamp", timestamp.isoformat(sep='T'))
        # set member values to send
        for membername, textmember in self.data.items():
            if membername in members:
                xmldata.append(textmember.onetext(members[membername]))
            else:
                xmldata.append(textmember.onetext(textmember.membervalue))
        return xmldata


    async def send_newTextVector(self, timestamp=None, members={}):
        """Transmits the vector (newTextVector) with members and values.
           members is a dictionary of membernames:text string values.
           The spec requires text vectors to be sent with all members, so if the given
           members dictionary only includes changed values, the remaining members with
           unchanged values will still be sent.
           This method will transmit the vector and change the vector state to busy.
           If no timestamp is given, a current UTC time will be created."""
        xmldata = self._newTextVector(timestamp, members)
        if xmldata is None:
            return
        self._timer = True
        self._newtimer = time.time()
        await self._client.send(xmldata)


class NumberVector(PropertyVector):
    """A NumberVector is used to send and receive numbers between instrument and client.
       As data is received, this vector is a mapping of membername:membervalue where membervalue
       is the string of the number taken from the received xml.
       The INDI spec defines a number of formats, including degrees:minutes:seconds so
       this class includes methods to obtain the number as a float, and to create a string
       formatted as the particular member requires.
       The member objects contain further information label, format spec, minimum, maximum and step size.
       To obtain the member object, as opposed to the member value, use the members() method."""

    def __init__(self, event):
        super().__init__(event.vectorname, event.label, event.group, event.state,
                         event.timestamp, event.message, event.device, event._client)
        self._perm = event.perm
        self.timeout = event.timeout
        # self.data is a dictionary of number name : numbermember
        # create  members
        for membername, membervalue in event.items():
            self.data[membername] = NumberMember(membername, *event.memberlabels[membername], membervalue)

    def getfloatvalue(self, membername):
        "Given a membername of this vector, returns the number as a float"
        if membername not in self:
            raise KeyError(f"Unrecognised member: {membername}")
        member = self.data[membername]
        return member.getfloatvalue()

    def getformattedvalue(self, membername):
        "Given a membername of this vector, returns the number as a formatted string"
        if membername not in self:
            raise KeyError(f"Unrecognised member: {membername}")
        member = self.data[membername]
        return member.getformattedvalue()

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    def _defvector(self, event):
        "Updates this vector with new values after a def... vector has been received"
        self._timer = False
        if event.label:
            self.label = event.label
        if event.group:
            self.group = event.group
        if event.perm:
            self.perm = event.perm
        if event.state:
            self.state = event.state
        if event.timestamp:
            self.timestamp = event.timestamp
        if event.message:
            self.message = event.message
        self.timeout = event.timeout
        # create  members
        for membername, membervalue in event.items():
            if membername in self.data:
                # update existing member
                if event.memberlabels[membername]:
                    member = self.data[membername]
                    member.label = event.memberlabels[membername][0]
                    member.format = event.memberlabels[membername][1]
                    member.min = event.memberlabels[membername][2]
                    member.max = event.memberlabels[membername][3]
                    member.step = event.memberlabels[membername][4]
                self.data[membername].membervalue = membervalue
            else:
                # create new member
                self.data[membername] = NumberMember(membername, *event.memberlabels[membername], membervalue)
        self.enable = True


    def _newNumberVector(self, timestamp=None, members={}):
        "Creates the xmldata for sending a newNumberVector"
        if not self.enable:
            return
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        if not isinstance(timestamp, datetime):
            # invalid timestamp given
            return
        if not (timestamp.tzinfo is None):
            if timestamp.tzinfo == timezone.utc:
                timestamp = timestamp.replace(tzinfo = None)
            else:
                # invalid timestamp
                return
        # timestamp has no tzinfo so isoformat does not include timezone info
        self.state = 'Busy'
        xmldata = ET.Element('newNumberVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("timestamp", timestamp.isoformat(sep='T'))
        # set member values to send
        for membername, numbermember in self.data.items():
            if membername in members:
                value = members[membername]
                if isinstance(value, float) or isinstance(value, int):
                    value = str(value)
                xmldata.append(numbermember.onenumber(value))
            else:
                xmldata.append(numbermember.onenumber(numbermember.membervalue))
        return xmldata

    async def send_newNumberVector(self, timestamp=None, members={}):
        """Transmits the vector (newNumberVector) with members and values.
           members is a dictionary of membernames:number values, the values can be
           integers, floats or strings, if not strings they will be converted to strings.
           The spec requires number vectors to be sent with all members, so if the given
           members dictionary only includes changed values, the remaining members with
           unchanged values will still be sent.
           This method will transmit the vector and change the vector state to busy.
           If no timestamp is given, a current UTC time will be created."""
        xmldata = self._newNumberVector(timestamp, members)
        if xmldata is None:
            return
        self._timer = True
        self._newtimer = time.time()
        await self._client.send(xmldata)



class BLOBVector(PropertyVector):

    """A BLOBVector is used to send and receive Binary Large Objects between instrument and client.
       As data is received this vector will be a mapping of membername to membervalue where membervalue
       will be a binary string of the received BLOB.  This binary string has been decoded from the
       received XML and from the b64 encoding used.
       The member object contains further information, label, blobsize and blobformat.
       To obtain the member object, as opposed to the member value, use the members() method."""

    def __init__(self, event):
        super().__init__(event.vectorname, event.label, event.group, event.state,
                         event.timestamp, event.message, event.device, event._client)
        self._perm = event.perm
        self.timeout = event.timeout
        # self.data is a dictionary of blob name : blobmember
        # create  members
        for membername, label in event.memberlabels.items():
            self.data[membername] = BLOBMember(membername, label)

    def set_blobsize(self, membername, blobsize):
        "Used when an event is received to set the member blobsize"
        if not isinstance(blobsize, int):
            return
        if membername in self.data:
            member = self.data[membername]
        else:
            return
        member.blobsize = blobsize

    def set_blobformat(self, membername, blobformat):
        """Sets the blobformat attribute in the blob member."""
        if membername in self.data:
            member = self.data[membername]
        else:
            return
        member.blobformat = blobformat

    @property
    def perm(self):
        return self._perm

    @perm.setter
    def perm(self, value):
        self._perm = self.checkvalue(value, ['ro','wo','rw'])

    def _defvector(self, event):
        "Updates this vector with new values after a def... vector has been received"
        self._timer = False
        if event.label:
            self.label = event.label
        if event.group:
            self.group = event.group
        if event.perm:
            self.perm = event.perm
        if event.state:
            self.state = event.state
        if event.timestamp:
            self.timestamp = event.timestamp
        if event.message:
            self.message = event.message
        self.timeout = event.timeout
        # create  members
        for membername, label in event.memberlabels.items():
            if membername in self.data:
                # update existing member
                self.data[membername].label = label
            else:
                # create new member
                self.data[membername] = BLOBMember(membername, label)
        self.enable = True


    def _setvector(self, event):
        "Updates this vector with new values after a setBLOBvector has been received"
        self._timer = False
        if not self.enable:
            # this property does not exist
            return
        super()._setvector(event)
        # set each members size and format
        # using event.sizeformat[membername] = (membersize, memberformat)
        for membername in event.keys():
            membersize, memberformat = event.sizeformat[membername]
            self.set_blobsize(membername, membersize)
            self.set_blobformat(membername, memberformat)


    def _newBLOBVector(self, timestamp=None, members={}):
        "Creates the xmldata for sending a newBLOBVector"
        if not self.enable:
            return
        if timestamp is None:
            timestamp = datetime.now(tz=timezone.utc)
        if not isinstance(timestamp, datetime):
            # invalid timestamp given
            return
        if not (timestamp.tzinfo is None):
            if timestamp.tzinfo == timezone.utc:
                timestamp = timestamp.replace(tzinfo = None)
            else:
                # invalid timestamp
                return
        # timestamp has no tzinfo so isoformat does not include timezone info
        self.state = 'Busy'
        xmldata = ET.Element('newBLOBVector')
        xmldata.set("device", self.devicename)
        xmldata.set("name", self.name)
        xmldata.set("timestamp", timestamp.isoformat(sep='T'))
        # set member values to send
        for membername, blobmember in self.data.items():
            if membername in members:
                # expand (value, blobsize, blobformat) to required arguments
                xmldata.append(blobmember.oneblob(*members[membername]))
        return xmldata

    async def send_newBLOBVector(self, timestamp=None, members={}):
        """Transmits the vector (newBLOBVector) with new BLOB members
           This method will transmit the vector and change the vector state to busy.
           The members dictionary should be {membername:(value, blobsize, blobformat)}
           The value could be a bytes object, a pathlib.Path or a file-like object.
           If blobsize of zero is used, the size value sent will be set to the number of bytes
           in the BLOB. The INDI standard specifies the size should be that of the BLOB
           before any compression, therefore if you are sending a compressed file, you
           should set the blobsize prior to compression.
           blobformat should be a file extension, such as '.png'"""
        xmldata = self._newBLOBVector(timestamp, members)
        if xmldata is None:
            return
        self._timer = True
        self._newtimer = time.time()
        await self._client.send(xmldata)
