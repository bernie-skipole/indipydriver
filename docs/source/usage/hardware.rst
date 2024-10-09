Hardware
========


The driver has method::

    async def hardware(self)

This  is started when the driver is run, and could be a long running co-routine, controlling whatever hardware is required, and calling appropriate vector methods to send data back to the client.

If a continuous loop is run in this hardware method, then use something like::

    while not self._stop:
        ...

The flag self._stop is set to True when the shutdown() method of the driver is called, so this exits the hardware co-routine.

Within this hardware method any vector can be accessed with::

    vector = self[devicename][vectorname]

A vectors member value can be updated, and sent to the client with::

     vector[membername] = newvalue
     await vector.send_setVector()

The send_setVector() method of a vector is obviously useful here, its arguments are::

    async def send_setVector(self, message='', timestamp=None, timeout=None, state=None, allvalues=True)

As default it sends the vector, including all its members to the client, the allvalues argument could be set to False::

     await vector.send_setVector(allvalues=False)

In which case, only values that have changed will be sent, saving bandwidth.

If no values have changed, the vector will not be sent, if you need to ensure the vector message, state or time values are sent to the client, then use the more explicit send_setVectorMembers method instead::

    async def send_setVectorMembers(self, message='', timestamp=None, timeout=None, state=None, members=[])

The members list specifies the member names which will have their values sent. If the members list is empty then a vector will still be sent, empty of members, which may be required if just a state or message is to be sent.

Please note that BLOBVectors do not have a send_setVector method only the more explicit send_setVectorMembers is available, this is to ensure more control over possibly large objects.


devhardware
^^^^^^^^^^^

If your driver contains several devices, it could be messy including the code to handle all the devices in the driver hardware method. You may find it simpler to delegate the hardware control to each device, separating the code to where it is most relevant.

The Device class has method::

    async def devhardware(self, *args, **kwargs):

You could subclass the Device class, and override this method to control the hardware of that particular device. To help in doing this, the constructor for each device has keyword dictionary 'devicedata' set as an attribute of the device, so when you create an instance of the device you can include any hardware related object required.

The driver hardware method would need to await each of the devices devhardware methods.

For example the driver hardware method would contain the line::

    await self[devicename].devhardware()

which awaits the device's devhardware method, containing the code to run that device. If you have multiple devices this could be done using the asyncio.gather function.

The args and kwargs arguments of devhardware are there so you can pass in any argument you like when calling this method.
