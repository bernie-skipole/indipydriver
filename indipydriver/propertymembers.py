
import math, pathlib

import xml.etree.ElementTree as ET

from base64 import standard_b64encode


def getfloat(value):
    """The INDI spec specifies several different number formats, given a number
       in any of these formats, this returns a float.
       If an error occurs while parsing the number, a TypeError exception is raised."""
    try:
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        if not isinstance(value, str):
            raise TypeError
        # negative is True, if the value is negative
        value = value.strip()
        negative = value.startswith("-")
        if negative:
            value = value.lstrip("-")
        # Is the number provided in sexagesimal form?
        if value == "":
            parts = ["0", "0", "0"]
        elif " " in value:
            parts = value.split(" ")
        elif ":" in value:
            parts = value.split(":")
        elif ";" in value:
            parts = value.split(";")
        else:
            # not sexagesimal
            parts = [value, "0", "0"]
        if len(parts) > 3:
            raise TypeError
        # Any missing parts should have zero
        if len(parts) == 1:
            parts.append("0")
            parts.append("0")
        if len(parts) == 2:
            parts.append("0")
        assert len(parts) == 3
        # a part could be empty string, ie if 2:5: is given
        numbers = list(float(x) if x else 0.0 for x in parts)
        floatvalue = numbers[0] + (numbers[1]/60) + (numbers[2]/3600)
        if negative:
            floatvalue = -1 * floatvalue
    except Exception:
        raise TypeError("Unable to parse number value")
    return floatvalue



class PropertyMember:
    "Parent class of SwitchMember etc"

    def __init__(self, name, label=None):
        if not name.isascii():
            raise ValueError("Member name should be all ascii characters.")
        self.name = name
        if label:
            self.label = label
        else:
            self.label = name
        # self.changed is a flag to indicate the value has changed
        # initially start with all values have changed
        self.changed = True

    def checkvalue(self, value, allowed):
        "allowed is a list of values, checks if value is in it"
        if value not in allowed:
            raise ValueError(f"Value \"{value}\" is not one of {str(allowed).strip('[]')}")
        return value


class SwitchMember(PropertyMember):
    """A SwitchMember can only have one of 'On' or 'Off' values"""

    def __init__(self, name, label=None, membervalue="Off"):
        super().__init__(name, label)
        # membervalue should be either 'Off' or 'On'
        self._membervalue = membervalue

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if not value:
            raise ValueError(f"The SwitchMember {self.name} value cannot be empty")
        newvalue = self.checkvalue(value, ['On', 'Off'])
        if self._membervalue != newvalue:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = newvalue

    def defswitch(self):
        """Returns a defSwitch"""
        xmldata = ET.Element('defSwitch')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._membervalue
        return xmldata

    def oneswitch(self):
        """Returns xml of a oneSwitch"""
        xmldata = ET.Element('oneSwitch')
        xmldata.set("name", self.name)
        xmldata.text = self._membervalue
        return xmldata


class LightMember(PropertyMember):
    """A LightMember can only have one of 'Idle', 'Ok', 'Busy' or 'Alert' values"""

    def __init__(self, name, label=None, membervalue="Idle"):
        super().__init__(name, label)
        self._membervalue = membervalue

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if not value:
            raise ValueError(f"The LightMember {self.name} value cannot be empty")
        newvalue = self.checkvalue(value, ['Idle','Ok','Busy','Alert'])
        if self._membervalue != newvalue:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = newvalue

    def deflight(self):
        """Returns xml of a defLight"""
        xmldata = ET.Element('defLight')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self._membervalue
        return xmldata

    def onelight(self):
        """Returns xml of a oneLight"""
        xmldata = ET.Element('oneLight')
        xmldata.set("name", self.name)
        xmldata.text = self._membervalue
        return xmldata


class TextMember(PropertyMember):
    """Contains a text string"""

    def __init__(self, name, label=None, membervalue=""):
        super().__init__(name, label)
        self._membervalue = membervalue

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if self._membervalue != value:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = value

    def deftext(self):
        """Returns a defText"""
        xmldata = ET.Element('defText')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.text = self.membervalue
        return xmldata

    def onetext(self):
        """Returns xml of a oneText"""
        xmldata = ET.Element('oneText')
        xmldata.set("name", self.name)
        xmldata.text = self.membervalue
        return xmldata


class NumberMember(PropertyMember):
    """Contains a number, the attributes inform the client how the number should be
       displayed.

       format is a C printf style format, for example %7.2f means the client should
       display the number string with seven characters (including the decimal point
       as a character and leading spaces should be inserted if necessary), and with
       two decimal digits after the decimal point.

       min is the minimum value

       max is the maximum, if min is equal to max, the client should ignore these.

       step is incremental step values, set to zero if not used.

       The above numbers, and the member value can be given as strings, which explicitly
       controls how numbers are placed in the xml protocol. If given as integers or floats
       they will be converted and set as strings.
    """

    def __init__(self, name, label=None, format='', min='0', max='0', step='0', membervalue='0'):
        super().__init__(name, label)
        self.format = format
        if isinstance(min, str):
            self.min = min
        else:
            self.min = str(min)
        if isinstance(max, str):
            self.max = max
        else:
            self.max = str(max)
        if isinstance(step, str):
            self.step = step
        else:
            self.step = str(step)
        if isinstance(membervalue, str):
            self._membervalue = membervalue
        else:
            self._membervalue = str(membervalue)


    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if not isinstance(value, str):
            value = str(value)
        if self._membervalue != value:
            # when a value has changed, set the changed flag
            self.changed = True
            self._membervalue = value


    def getfloatvalue(self):
        """The INDI spec allows a number of different number formats, this method returns
           this members value as a float.
           If an error occurs while parsing the number, a TypeError exception is raised."""
        return getfloat(self._membervalue)


    def getformattedvalue(self):
        """This method returns this members value as a formatted string.
           If an error occurs while parsing the number, a TypeError exception is raised."""
        floatval = getfloat(self._membervalue)
        return self.format_number(floatval)


    def format_number(self, value):
        """This takes a float, and returns a formatted string
        """
        if (not self.format.startswith("%")) or (not self.format.endswith("m")):
            return self.format % value
        # sexagesimal format
        if value<0:
            negative = True
            value = abs(value)
        else:
            negative = False
        # number list will be degrees, minutes, seconds
        number_list = [0,0,0]
        if isinstance(value, int):
            number_list[0] = value
        else:
            # get integer part and fraction part
            fractdegrees, degrees = math.modf(value)
            number_list[0] = int(degrees)
            mins = 60*fractdegrees
            fractmins, mins = math.modf(mins)
            number_list[1] = int(mins)
            number_list[2] = 60*fractmins

        # so number list is a valid degrees, minutes, seconds
        # degrees
        if negative:
            number = f"-{number_list[0]}:"
        else:
            number = f"{number_list[0]}:"
        # format string is of the form  %<w>.<f>m
        w,f = self.format.split(".")
        w = w.lstrip("%")
        f = f.rstrip("m")
        if (f == "3") or (f == "5"):
            # no seconds, so create minutes value
            minutes = float(number_list[1]) + number_list[2]/60.0
            if f == "5":
                number += f"{minutes:04.1f}"
            else:
                number += f"{minutes:02.0f}"
        else:
            number += f"{number_list[1]:02d}:"
            seconds = float(number_list[2])
            if f == "6":
                number += f"{seconds:02.0f}"
            elif f == "8":
                number += f"{seconds:04.1f}"
            else:
                number += f"{seconds:05.2f}"

        # w is the overall length of the string, prepend with spaces to make the length up to w
        w = int(w)
        lth = len(number)
        if w>lth:
            number = " "*(w-lth) + number
        return number

    def defnumber(self):
        """Returns a defNumber"""
        xmldata = ET.Element('defNumber')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        xmldata.set("format", self.format)
        xmldata.set("min", self.min)
        xmldata.set("max", self.max)
        xmldata.set("step", self.step)
        xmldata.text = self._membervalue
        return xmldata

    def onenumber(self):
        """Returns xml of a oneNumber"""
        xmldata = ET.Element('oneNumber')
        xmldata.set("name", self.name)
        xmldata.text = self._membervalue
        return xmldata


class BLOBMember(PropertyMember):
    """Contains a 'binary large object' such as an image. The membervalue
       should be either None, a bytes object, a file-like object, or a path
       to a file.

       Typically membervalue is left at None when creating a member, and only
       set to a value via vector[membername] = membervalue prior to calling
       the vector send_setVectorMembers method.

       blobsize is the size of the BLOB before any compression, if left at
       zero, the length of the BLOB will be used. The member blobsize can be
       set by calling the vector.set_blobsize(membername, blobsize) method.

       The BLOB format should be a string describing the BLOB, such as .jpeg
    """

    def __init__(self, name, label=None, blobsize=0, blobformat='', membervalue=None):
        super().__init__(name, label)
        if not isinstance(blobsize, int):
            raise ValueError(f"The BLOBMember {self.name} blobsize must be an integer object")
        # membervalue can be a byte string, path, string path or file like object
        self._membervalue = membervalue
        self.blobsize = blobsize
        self.blobformat = blobformat

    @property
    def membervalue(self):
        return self._membervalue

    @membervalue.setter
    def membervalue(self, value):
        if not value:
            raise ValueError(f"The BLOBMember {self.name} value cannot be empty")
        self._membervalue = value

    def defblob(self):
        """Returns a defBlob, does not contain a membervalue"""
        xmldata = ET.Element('defBLOB')
        xmldata.set("name", self.name)
        xmldata.set("label", self.label)
        return xmldata


    def oneblob(self, value=None):
        """Returns xml of a oneBLOB
           If value is None, then uses membervalue as the value
           otherwise uses the value given"""
        xmldata = ET.Element('oneBLOB')
        xmldata.set("name", self.name)
        # the value set in the xmldata object should be a bytes object
        if value is None:
            bytescontent = self.getbytes(self._membervalue)
        else:
            bytescontent = self.getbytes(value)

        if self.blobformat:
            xmldata.set("format", self.blobformat)
        elif (value is None) or isinstance(value, bytes):
            # no self.blobformat available, if possible get it from self._membervalue
            if isinstance(self._membervalue, pathlib.Path):
                xmldata.set("format", "".join(self._membervalue.suffixes) )
            elif isinstance(self._membervalue, str):
                xmldata.set("format", "".join(pathlib.Path(self._membervalue).suffixes) )
            else:
                xmldata.set("format", "")
        elif isinstance(value, pathlib.Path):
            xmldata.set("format", "".join(value.suffixes) )
        elif isinstance(value, str):
            xmldata.set("format", "".join(pathlib.Path(value).suffixes) )
        else:
            xmldata.set("format", "")
        if not self.blobsize:
            self.blobsize = len(bytescontent)
        xmldata.set("size", str(self.blobsize))
        xmldata.text = standard_b64encode(bytescontent).decode("utf-8")
        return xmldata


    @staticmethod
    def getbytes(value):
        "Given a blob value, as bytes or file path, return the bytes"
        if not value:
            raise ValueError("The BLOB value is empty")
        try:
            if isinstance(value, bytes):
                bytescontent = value
            elif isinstance(value, pathlib.Path):
                bytescontent = value.read_bytes()
            elif hasattr(value, "seek") and hasattr(value, "read") and callable(value.read):
                # a file-like object
                # set seek(0) so is read from start of file
                value.seek(0)
                bytescontent = value.read()
                value.close()
            else:
                # could be a path to a file
                with open(value, "rb") as fp:
                    bytescontent = fp.read()
        except Exception:
            raise ValueError("Unable to read the given BLOB value")

        if not isinstance(bytescontent, bytes):
            raise ValueError("On being read, the BLOB value does not give bytes")
        if not bytescontent:
            raise ValueError("The BLOB value is empty")

        return bytescontent
