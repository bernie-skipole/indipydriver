Example5
========

This example expands on the thermostat with a switch vector and a BLOB vector. A switch is added so the client can request logfiles which will be sent as BLOB's at regular intervals.

An io.BytesIO buffer is set with temperature logs every second. After five minutes a new buffer is started. Since buffers are started, completed and sent asynchronously, they are placed in a deque, which is tested frequently, and the oldest buffer sent when available.::


    import asyncio, io, collections

    from datetime import datetime, timezone, timedelta

    from indipydriver import (IPyDriver, Device,
                              NumberVector, NumberMember,
                              getProperties, newNumberVector,
                              BLOBVector, BLOBMember,
                              SwitchVector, SwitchMember, newSwitchVector,
                              IPyServer
                             )

    class ThermalControl:
        """This is a simulation containing variables only, normally it
           would control a real heater, and take temperature measurements
           from a sensor."""

        def __init__(self, txque):
            """Set start up values, txque is an asyncio.Queue object
               used to transmit temperature readings """
            self.temperature = 20
            self.target = 15
            self.heater = "Off"
            self.txque = txque

            # logfiles (BytesIO buffers) will be created
            # containing logs, and the buffer will be sent
            # as a BLOB to the client at intervals set here

            self.delta = timedelta(minutes=5)
            # change minutes value for different logfile period
            self.logtime = datetime.now(tz=timezone.utc) + self.delta

            self._enablelogs = False
            self.logfiles = collections.deque(maxlen=4)
            # self.logfiles is a deque containing a number of io.BytesIO objects
            # with the number limited to 4, so the latest is the current buffer
            # to which logs will be added, and the older buffers can be sent
            # to the client, or if not taken off, will be discarded.

            # Start with enablelogs False, and no buffer in the deque.

        @property
        def enablelogs(self):
            return self._enablelogs

        @enablelogs.setter
        def enablelogs(self, value):
            "Enable log collection"
            if value == self._enablelogs:
                # no change
                return
            self._enablelogs = value
            if value:
                # logging turned on, create a buffer to be populated
                self.logfiles.append(io.BytesIO())
                # and set time for new buffer to be created
                self.logtime = datetime.now(tz=timezone.utc) + self.delta
            else:
                # logging turned off, empty the deque, close io.BytesIO objects
                while True:
                    try:
                        b = self.logfiles.popleft()
                        b.close()
                    except IndexError:
                        break

        @property
        def logswitch(self):
            "Return logging status as a switch string"
            if self._enablelogs:
                return "On"
            else:
                return "Off"

        def get_logfile(self):
            "If a finished logfile is available, return it, otherwise return None"
            # get the oldest logfile and return it
            # don't get the current buffer, hence check len greater than 1
            if len(self.logfiles) > 1:
                return self.logfiles.popleft()

        def appendlog(self, timestamp, temperature):
            """Appends a log to the current buffer, and every delta
               time create a new buffer
               """
            if not self._enablelogs:
                # logs disabled
                return

            # If logtime is reached, create new current buffer
            if timestamp > self.logtime:
                # set a new buffer into self.logfiles
                self.logfiles.append(io.BytesIO())
                # and set logtime to delta time in the future
                self.logtime = timestamp + self.delta

            stringtemperature = '{:.2f}'.format(temperature)

            # log time/temp into the current buffer which is at self.logfiles[-1],
            # this being the most recent buffer
            log = timestamp.isoformat(sep='T')[:21] + "," + stringtemperature + "\n"
            self.logfiles[-1].write(log.encode())


        async def poll_thermostat(self):
            """This simulates temperature increasing/decreasing, and turns
               on/off a heater if moving too far from the target."""
            while True:
                await asyncio.sleep(10)
                if self.heater == "On":
                    # increasing temperature if the heater is on
                    self.temperature += 0.2
                else:
                    # decreasing temperature if the heater is off
                    self.temperature -= 0.2

                if self.temperature > self.target+0.5:
                    # too hot
                    self.heater = "Off"

                if self.temperature < self.target-0.5:
                    # too cold
                    self.heater = "On"

                # transmit the temperature and timestamp back to the client
                timestamp = datetime.now(tz=timezone.utc)
                senddata = (timestamp, self.temperature)

                # append a log line
                self.appendlog(timestamp, self.temperature)

                # send the same data to the client
                try:
                    self.txque.put_nowait(senddata)
                except asyncio.QueueFull:
                    # if the queue is full, perhaps due to
                    # communications problems, simply drop the
                    # record, but keep operating the thermostat
                    pass


    class ThermoDriver(IPyDriver):

        """IPyDriver is subclassed here, with two methods created to handle incoming events
           and to transmit the temperature to the client"""

        async def clientevent(self, event):
            """On receiving data, this is called, and should handle any necessary actions
               The event object has property 'vector' which is the propertyvector being
               updated or requested by the client.
               """

            thermalcontrol = self.driverdata["thermalcontrol"]

            match event:
                case getProperties():
                    await event.vector.send_defVector()

                case newNumberVector(devicename='Thermostat',
                                     vectorname='targetvector') if 'target' in event:
                    # Set the received value as the thermostat target
                    newtarget = event['target']
                    # The self.indi_number_to_float method converts the received string,
                    # which may be in a number of formats to a Python float value. This
                    # can then be set into thermalcontrol
                    try:
                        target = self.indi_number_to_float(newtarget)
                    except TypeError:
                        # ignore an incoming invalid number
                        pass
                    else:
                        # set new target
                        thermalcontrol.target = target
                        # and set the new target value into the vector member,
                        # then transmit the vector back to client.
                        event.vector['target'] = '{:.2f}'.format(target)
                        await event.vector.send_setVector()

                case newSwitchVector(devicename='Thermostat',
                                     vectorname='switchvector') if "switchmember" in event:
                    if event["switchmember"] == "On":
                        thermalcontrol.enablelogs = True
                    elif event["switchmember"] == "Off":
                        thermalcontrol.enablelogs = False
                    # setting the switch value into the vector updates the client
                    event.vector["switchmember"] = thermalcontrol.logswitch
                    await event.vector.send_setVector()
                    await self['Thermostat'].send_device_message(message=f"Log reporting is now {thermalcontrol.logswitch}")


        async def hardware(self):
            """This is a continuously running coroutine which is used
               to transmit the temperature to connected clients."""

            thermalcontrol = self.driverdata["thermalcontrol"]
            txque = self.driverdata["txque"]
            temperaturevector = self['Thermostat']['temperaturevector']
            logsvector = self['Thermostat']['logsvector']
            while True:
                # wait until an item is available in txque
                timestamp,temperature = await txque.get()
                # Numbers need to be explicitly set in the indi protocol
                # so need to send a string version
                stringtemperature = '{:.2f}'.format(temperature)
                # set this new value into the vector
                temperaturevector['temperature'] = stringtemperature
                # and transmit it to the client
                await temperaturevector.send_setVector(timestamp=timestamp)
                # Notify the queue that the work has been processed.
                txque.task_done()

                # if a logfile is available, send it as a BLOB
                logfile = thermalcontrol.get_logfile()
                # this returns None if no logfile is currently available
                if logfile:
                    logsvector["templogs"] = logfile
                    # send the blob
                    await logsvector.send_setVectorMembers(members=["templogs"])



    def make_driver():
        "Returns an instance of the driver"

        # create a queue to transmit from thermalcontrol
        txque = asyncio.Queue(maxsize=5)

        thermalcontrol = ThermalControl(txque)

        # create a vector with one number 'temperaturemember' as its member

        # Note: numbers must be given as strings
        stringtemperature = '{:.2f}'.format(thermalcontrol.temperature)
        temperaturemember = NumberMember( name="temperature",
                                          format='%3.1f', min='-50', max='99',
                                          membervalue=stringtemperature )
        # Create a NumberVector instance, containing the member.
        temperaturevector = NumberVector( name="temperaturevector",
                                          label="Temperature",
                                          group="Values",
                                          perm="ro",
                                          state="Ok",
                                          numbermembers=[temperaturemember] )

        # create a vector with one number 'targetmember' as its member
        stringtarget = '{:.2f}'.format(thermalcontrol.target)
        targetmember = NumberMember( name="target",
                                     format='%3.1f', min='-50', max='99',
                                     membervalue=stringtarget )
        targetvector = NumberVector( name="targetvector",
                                     label="Target",
                                     group="Values",
                                     perm="rw",
                                     state="Ok",
                                     numbermembers=[targetmember] )

        # note the targetvector has permission rw so the client can set it

        # create blobvector, there is no membervalue to set at this point
        logsmember = BLOBMember( name="templogs",
                                 label="Temperature logs",
                                 blobformat = ".csv" )
        logsvector = BLOBVector( name="logsvector",
                                 label="Logs",
                                 group="Control",
                                 perm="ro",
                                 state="Ok",
                                 blobmembers=[logsmember] )

        # create a switchvector so client can turn on/off log reporting
        logswitchmember = SwitchMember( name="switchmember", label="Logs",
                                        membervalue=thermalcontrol.logswitch )
        logswitchvector = SwitchVector( name="switchvector",
                                        label="Logs Control",
                                        group="Control",
                                        perm="rw",
                                        rule = "AtMostOne",
                                        state="Ok",
                                        switchmembers=[logswitchmember] )

        # create a device with these vectors
        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector,
                                         targetvector,
                                         logsvector,
                                         logswitchvector] )

        # set the coroutine to be run with the driver
        pollingtask = thermalcontrol.poll_thermostat()

        # Create the Driver, containing this device and
        # other objects needed to run the instrument
        driver = ThermoDriver( devices=[thermostat],
                               tasks=[pollingtask],
                               txque=txque,
                               thermalcontrol=thermalcontrol )

        # and return the driver
        return driver


    if __name__ == "__main__":

        driver = make_driver()
        server = IPyServer([driver], host="localhost", port=7624, maxconnections=5)
        asyncio.run(server.asyncrun())
