Concept
=======

The INDI protocol (Instrument Neutral Distributed Interface) specifies a limited number of ways data can be presented, as switches, lights, text, numbers and BLOBs (Binary Large Objects), together with grouping and label values which are used to display the data.

As the protocol contains the format of the data, a client learns and presents the controls when it connects.

This 'indipydriver' package provides classes which take values from your own code and serves the protocol, handling connections from clients.

In general, a client transmits a 'getProperties' request, and this indipydriver responds to this with definition packets (defSwitchVector, defLightVector, .. ) that define the format of the instrument data.

As the instrument produces changing values, you would call the appropriate methods to send 'set' packets, such as setSwitchVector, setLightVector ..., which contain the new values, and which the client will receive.

The client can send 'new' packets to set new values to the instrument. The IPyDriver object has a rxevent method which is called as new properties are received, and which you can use to control your instrument.

A typical driver program will be structured as:

.. image:: ./images/concept.png

There are further facilities available; in which one driver can monitor (snoop) on the output of another driver, the server object can use third party drivers, and can also connect to remote servers and drivers, creating a network of instruments:

.. image:: ./images/rem2.png


indipyclient
^^^^^^^^^^^^

The associated package indipyclient will be installed automatically with indipydriver, and can be installed separately from Pypi.

https://pypi.org/project/indipyclient

This is a client library providing functions which communicate to an INDI service, and can be used to write scripts to view and control your instruments.

The indipyclient can also be run using

python3 -m indipyclient [options]

In which case it provides a terminal client using Python standard library curses module (Linux only).

A typical session would look like:

.. image:: ./images/image1.png

Further information about indipyclient can be found from:

https://indipyclient.readthedocs.io


indipyterm
^^^^^^^^^^

The associated package indipyterm provides a more useful terminal client, using the 'textual' library, and is available from

https://pypi.org/project/indipyterm

The client can be run from a virtual environment with

indipyterm [options]

or with

python3 -m indipyterm [options]

The package help is:

.. code-block:: text

    usage: indipyterm [options]

    Terminal client to communicate to an INDI service.

    options:
      -h, --help               show this help message and exit
      --port PORT              Port of the INDI server (default 7624).
      --host HOST              Hostname/IP of the INDI server (default localhost).
      --blobfolder BLOBFOLDER  Optional folder where BLOB's will be saved.

      --version    show program's version number and exit

A typical session would look like:

.. image:: ./images/image2.png

Further information about indipyterm can be found from:

https://github.com/bernie-skipole/indipyterm
