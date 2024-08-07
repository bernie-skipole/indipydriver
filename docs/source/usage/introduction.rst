Introduction
============


indipydriver
^^^^^^^^^^^^

This is a pure python package, providing a set of classes which can be used to create an INDI driver and serve the INDI communications protocol on a port.

It has one dependency, indipyclient, which itself is pure python and has no further dependencies.

INDI - Instrument Neutral Distributed Interface.

For further information on INDI, see :ref:`references`.

Typically you would use this package to create drivers to control an instrument, or GPIO pins on the computer itself, and the package functions generate the INDI protocol which communicates to an INDI client.

Installing indipydriver from Pypi will also install indipyclient which provides a terminal client so the instrument can be viewed and controlled from a terminal session. The INDI protocol is defined so that drivers should operate with any INDI client. The indipyclient package can also be installed separately on a remote computer.

The protocol defines the format of the data sent, such as light, number, text, switch or BLOB (Binary Large Object) and the client can send commands to control the instrument.  The client takes the format of switches, numbers etc., from the protocol.

INDI is often used with astronomical instruments, but is a general purpose protocol which can be used for any instrument control if appropriate drivers are written.

The driver object created contains 'device' objects, each of which can contain 'vector' objects, such as a SwitchVector or LightVector. These Vector objects can contain one or more 'members', such as a number of 'switches', or a number of 'lights'.

The package can be installed from:

https://pypi.org/project/indipydriver

Usually you would install into a virtual environment, if using a Raspberry Pi you may want your environment to be able to access the system gpiozero module, so it is suggested you create a virtual environment something like::

    python3 -m venv --system-site-packages ~/myenv

and then::

    source ~/myenv/bin/activate

Followed by::

    pip install indipydriver

You can then change to a directory of your choice where you will be developing your script.

Typically you would create a subclass of IPyDriver.

The driver has methods which should be overwritten.

**async def rxevent(self, event)**

This is called whenever data is received from the client, typically to set an instrument parameter. The event object describes the received data, and you provide the code which then controls your instrument.

**async def hardware(self)**

This should be a contuously running coroutine which you can use to operate your instruments, and if required send updates to the client.

**async def snoopevent(self, event)**

This is only used if the device is monitoring (snooping) on other devices.

The indipydriver package also includes an IPyServer class. Having created an instance of your IPyDriver subclass, you would serve this, and any other drivers with an IPyServer object::

    server = IPyServer(driver, host="localhost", port=7624, maxconnections=5)
    await server.asyncrun()

A connected client, such as indipyclient, can then control all the drivers.

The IPyServer can also run third party INDI drivers created with other languages or tools, using an add_exdriver method. It also has an add_remote method which can be used to add connections to remote servers, creating a tree network of servers.
