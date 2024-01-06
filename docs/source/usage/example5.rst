Example5
========

This example expands on the thermostat with a switch vector and a BLOB vector. A switch is added so the client can request logfiles which will be sent as BLOB's at regular intervals.

An io.BytesIO buffer is set with temperature logs every second. After five minutes a new buffer is started. Since buffers are started, completed and sent asynchronously, they are placed in a deque, which is tested frequently, and the oldest buffer sent when available.::


    import asyncio, io, collections, datetime

    from indipydriver import (IPyDriver, Device,
                              NumberVector, NumberMember,
                              getProperties, newNumberVector,
                              LightVector, LightMember,
                              BLOBVector, BLOBMember,
                              SwitchVector, SwitchMember, newSwitchVector
                             )

    class ThermalControl:
        "This is a simulation containing variables only"

        def __init__(self):
            "Set start up values"
            self.temperature = 20
            self.target = 15
            self.heater = "On"

            # logfiles (BytesIO buffers) will be created
            # containing logs, and the buffer will be sent
            # as a BLOB to the client at intervals set here

            self.delta = datetime.timedelta(minutes=5)
            # change minutes value for different logfile period
            self.logtime = datetime.datetime.utcnow() + self.delta

            self._enablelogs = False
            self.logfiles = collections.deque(maxlen=4)
            # self.logfiles is a deque containing a number of io.BytesIO objects
            # with the number limited to 4, so the latest is the current buffer
            # to which logs will be added, and the older buffers can be sent
            # to the client.

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
                self.logtime = datetime.datetime.utcnow() + self.delta
            else:
                # logging turned off, empty the deque
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

        def appendlog(self):
            """Appends a log to the current buffer, and every delta
               time create a new buffer
               """
            if not self._enablelogs:
                # logs disabled
                return

            # If logtime is reached, create new current buffer
            nowtime = datetime.datetime.utcnow()
            if nowtime > self.logtime:
                # set a new buffer into self.logfiles
                self.logfiles.append(io.BytesIO())
                # and set delta time to 5 mins in the future
                self.logtime = nowtime + self.delta

            # log time/temp into the current buffer which is at self.logfiles[-1],
            # this being the most recent buffer
            log = nowtime.isoformat(sep='T')[:21] + "," + self.stringtemperature + "\n"
            self.logfiles[-1].write(log.encode())

        @property
        def stringtemperature(self):
            "Gives temperature as a string to two decimal places"
            return '{:.2f}'.format(self.temperature)

        @property
        def stringtarget(self):
            "Gives target as a string to two decimal places"
            return '{:.2f}'.format(self.target)

        async def poll_thermostat(self):
            """This simulates temperature increasing/decreasing, and turns
               on/off a heater if moving too far from the target."""
            while True:
                await asyncio.sleep(1)
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

                # and append a log line
                self.appendlog()



    class ThermoDriver(IPyDriver):

        """IPyDriver is subclassed here, with two methods created to handle incoming events
           and to control and monitor the instrument hardware"""

        async def clientevent(self, event):
            """On receiving data, this is called, and should handle any necessary actions."""

            # The hardware control object is stored in the driverdata dictionary
            control = self.driverdata["control"]

            match event:
                case getProperties():
                    await event.vector.send_defVector()

                case newNumberVector(devicename='Thermostat',
                                     vectorname='targetvector') if 'target' in event:
                    newtarget = event['target']
                    try:
                        target = self.indi_number_to_float(newtarget)
                    except TypeError:
                        # ignore an incoming invalid number
                        pass
                    else:
                        control.target = target
                        event.vector['target'] = control.stringtarget
                        event.vector.state = 'Ok'
                        await event.vector.send_setVector()
                        # If the target is below 5C, and if the temperature is still
                        # above 5.0, warn of the danger of frost due to the target being low
                        statusvector = self['Thermostat']['statusvector']
                        if target < 5.0 and control.temperature > 5.0:
                            statusvector["frost"] = 'Idle'
                            await statusvector.send_setVector(allvalues=False)
                            await self['Thermostat'].send_device_message(message="Setting a target below 5C risks frost damage")

                case newSwitchVector(devicename='Thermostat',
                                     vectorname='switchvector') if "switchmember" in event:
                    if event["switchmember"] == "On":
                        control.enablelogs = True
                    elif event["switchmember"] == "Off":
                        control.enablelogs = False
                    # sending 'Ok' informs the client that the value has been received
                    # and setting the switch value into the vector updates the client switch
                    event.vector.state = 'Ok'
                    event.vector["switchmember"] = control.logswitch
                    await event.vector.send_setVector()
                    await self['Thermostat'].send_device_message(message=f"Log reporting is now {control.logswitch}")


        async def hardware(self):
            "Run the hardware"
            # run the thermostat polling task
            control = self.driverdata["control"]
            poll_task = asyncio.create_task(control.poll_thermostat())

            # report temperature and status every ten seconds
            device = self['Thermostat']
            temperaturevector = device['temperaturevector']
            statusvector = device['statusvector']
            logsvector = device['logsvector']
            while True:
                await asyncio.sleep(10)

                # set the string temperature into the temperature vector
                temperaturevector['temperature'] = control.stringtemperature
                await temperaturevector.send_setVector()

                temperature = control.temperature

                # Now set the status lights.
                if temperature < 5.0:
                    statusvector["frost"] = "Alert"
                elif control.target < 5.0:
                    # frost is not emminent, but show Idle light as warning
                    # that the target is set too low, causing a risk of frost.
                    statusvector["frost"] = "Idle"
                else:
                    statusvector["frost"] = "Ok"
                if temperature > 30.0:
                    statusvector["hot"] = "Alert"
                else:
                    statusvector["hot"] = "Ok"
                if control.heater == "On":
                    statusvector["heater"] = "Busy"
                else:
                    statusvector["heater"] = "Ok"
                # send this vector, but with allvalues=False so it
                # is only sent as the values change
                await statusvector.send_setVector(allvalues=False)

                # if a logfile is available, send it as a BLOB
                logfile = control.get_logfile()
                # this returns None if no logfile is currently available
                if logfile:
                    logsvector["templogs"] = logfile
                    # send the blob
                    await logsvector.send_setVectorMembers(members=["templogs"])


    def make_driver():
        "Creates the driver"

        # create hardware object
        thermalcontrol = ThermalControl()

        # create a vector with one number 'temperature' as its member
        temperature = NumberMember(name="temperature", format='%3.1f', min='-50', max='99',
                                   membervalue=thermalcontrol.stringtemperature)
        temperaturevector = NumberVector( name="temperaturevector",
                                          label="Temperature",
                                          group="Values",
                                          perm="ro",
                                          state="Ok",
                                          numbermembers=[temperature] )

        # create a vector with one number 'target' as its member
        target = NumberMember(name="target", format='%3.1f', min='-50', max='99',
                              membervalue=thermalcontrol.stringtarget)
        targetvector = NumberVector( name="targetvector",
                                     label="Target",
                                     group="Values",
                                     perm="rw",
                                     state="Ok",
                                     numbermembers=[target] )

        frost = LightMember(name="frost", label="Frost Warning")
        hot = LightMember(name="hot", label="Over heating Warning")
        heater = LightMember(name="heater", label="Heater")

        # set these members into a vector
        statusvector = LightVector( name="statusvector",
                                    label="Status",
                                    group="Values",
                                    state="Ok",
                                    lightmembers=[frost, hot, heater] )


        # create blobvector, there is no membervalue to set at this point
        logs = BLOBMember(name="templogs", label="Temperature logs", blobformat = ".csv")
        logsvector = BLOBVector(name="logsvector",
                                label="Logs",
                                group="Control",
                                perm="ro",
                                state="Ok",
                                blobmembers=[logs] )

        # create a switchvector so client can turn on/off log reporting
        logswitchmember = SwitchMember(name="switchmember", label="Logs",
                                       membervalue=thermalcontrol.logswitch)
        logswitchvector = SwitchVector( name="switchvector",
                                        label="Logs Control",
                                        group="Control",
                                        perm="rw",
                                        rule = "AtMostOne",
                                        state="Ok",
                                        switchmembers=[logswitchmember] )


        thermostat = Device( devicename="Thermostat",
                             properties=[temperaturevector,
                                         targetvector,
                                         statusvector,
                                         logsvector,
                                         logswitchvector] )

        # Create the Driver, containing this device, and the hardware control object
        driver = ThermoDriver(devices=[thermostat],  control=thermalcontrol)

        # and return the driver
        return driver


    if __name__ == "__main__":

        driver = make_driver()
        asyncio.run(driver.asyncrun())
