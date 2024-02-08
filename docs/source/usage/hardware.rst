Hardware
========


The driver has method::

    async def hardware(self)

This  is started when the driver is run, and should be a long running co-routine, controlling whatever hardware is required, and calling appropriate vector methods to send data.

Within this hardware method any vector can be accessed with::

    vector = self[devicename][vectorname]

A vectors member value can be updated, and sent to the client with::

     vector[membername] = newvalue
     await vector.send_setVector()


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
