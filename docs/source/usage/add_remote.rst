add_remote
==========

The IPyServer class has method add_remote which can make a connection to a remote INDI service and its drivers.

A typical layout might be:

.. image:: ./images/rem1.png

In this scenario the client can control all the drivers, and any of the drivers can 'snoop' on any other.

It is an implementation detail that the client communicates to drivers in the direction in which calls are created, that is, from client to IPyServer A, and via the remote connection call, from IPyServer A to IPyServer B

If the client connected directly to IPyServer B, it would not be able to communicate to Drivers A and B since that is against the direction in which the remote call, from IPyServer A to IPyServer B, is made.

Great care must be taken not to introduce a network loop, otherwise traffic would circulate.

Another layout might be:

.. image:: ./images/rem2.png

In this case Driver E is 'Listening' on a port, rather than using IPyServer, this reduces the code involved in running the driver.
