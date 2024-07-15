indipyclient
============

If indipydriver is installed from Pypi, the package indipyclient will also be automatically installed.

This is a terminal client which communicates to an INDI service, and can be used to view and control your instruments. It can also be installed separately from the indipydriver package and is available at:

https://pypi.org/project/indipyclient

The client can be run with

indipyclient [options]

or with

python3 -m indipyclient [options]

The package help is::

    usage: indipyclient [options]

    Terminal client to communicate to an INDI service.

    options:
      -h, --help            show this help message and exit
      -p PORT, --port PORT  Port of the INDI server (default 7624).
      --host HOST           Hostname/IP of the INDI server (default localhost).
      -b BLOBS, --blobs BLOBS
                            Optional folder where BLOB's will be saved.
      --loglevel LOGLEVEL   Enables logging, value 1, 2, 3 or 4.
      --logfile LOGFILE     File where logs will be saved
      --version             show program's version number and exit

    The BLOB's folder can also be set from within the session.
    Setting loglevel and logfile should only be used for brief
    diagnostic purposes, the logfile could grow very big.
    loglevel:1 Information and error messages only,
    loglevel:2 As 1 plus xml vector tags without members or contents,
    loglevel:3 As 1 plus xml vectors and members - but not BLOB contents,
    loglevel:4 As 1 plus xml vectors and all contents


A typical sesssion would look like:

.. image:: ./images/image1.png

As well as the terminal client, the indipyclient package can be imported into your own script and provides a set of classes which can generate the INDI protocol and create the connection to a port serving INDI drivers. This could be used to create your own client, or to control remote instruments with your own Python program.

Further information about indipyclient can be found from:

https://indipyclient.readthedocs.io
