Auto Web serving
================

Assuming you have a script, myscript.py, containing your project, together with any modules packages etc, and you want to have it automatically start.

You also want the project to be served with indipyweb, and be served with a reverse proxy nginx.

Serving using nginx is particularly useful on a Debian system, as nginx can be installed, and automatically run listening on port 80, which is otherwise awkward since the root user is needed to access ports below 1000.

Create a projectfiles directory, beneath your home directory to hold your files:

~/projectfiles

Copy your project files into this directory, and cd into it.

Create a virtual environment:

python3 -m venv .venv

Or, if you are using system packages such as gpiozero:

python3 -m venv --system-site-packages .venv

and activate the environment:

source .venv/bin/activate

Then install your dependencies

pip install indipydriver

pip install indipyserver

pip install indipyweb

and any other requirements you may have. Then deactivate

deactivate

You now need to create a systemd file to start this

So to create a file:

/lib/systemd/system/myproj.service

cd to /lib/systemd/system/

Then use nano::

    sudo nano myproj.service

To make a file myproj.service with the following contents::

    [Unit]
    Description=My project description
    After=multi-user.target

    [Service]
    Type=idle
    ExecStart=/home/username/projectfiles/.venv/bin/python /home/username/projectfiles/myscript.py

    User=username

    Restart=on-failure

    # Connects standard output to /dev/null
    StandardOutput=null

    # Connects standard error to journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target


Swap out 'username' in the above text for your own username. Save it and exit nano. Enable the service

sudo systemctl daemon-reload

sudo systemctl enable myproj.service

This starts /home/username/projectfiles/myscript.py on boot up.

Finally reboot.

Test this using indipyterm to connect to localhost:7624, and your INDI service should be working.

Now, in a similar manner, create an indipyweb service.

create a file:

/lib/systemd/system/indipyweb.service


containing the following::

    [Unit]
    Description=Runs indipyweb
    After=multi-user.target

    [Service]
    Type=idle
    ExecStart=/home/username/projectfiles/.venv/bin/python -m indipyweb --dbfolder /home/username/projectfiles

    User=username

    Restart=on-failure

    # Connects standard output to /dev/null
    StandardOutput=null

    # Connects standard error to journal
    StandardError=journal

    [Install]
    WantedBy=multi-user.target

And follow the same steps to enable indipyweb.service.

sudo systemctl daemon-reload

sudo systemctl enable indipyweb.service

Once rebooted you should be able (from a local browser) to connect to localhost:8000, and see your service running.

You now want nginx, to serve on port 80, and be able to access it anywhere on your network. nginx can be loaded with the system apt, and will be automatically started.

sudo apt-get install nginx

Use your browser to connect to 'localhost' and you should see the nginx web service running on the normal port 80::

        Welcome to nginx!

        If you see this page, the nginx web server is successfully installed and working. Further configuration is required.

        For online documentation and support please refer to nginx.org.
        Commercial support is available at nginx.com.

        Thank you for using nginx.

So nginx is running and serving a default web page. We now need it to proxy requests to port 8000. A Debian based system has two directories:

/etc/nginx/sites-available

/etc/nginx/sites-enabled

You will see under sites-available a default configuration file, and under sites-enabled a link to that file, which is the current enabled default site.

Under /etc/nginx/sites-available create another configuration file myproj.conf::


 server  {

    server_name _;

    listen 80;
    location / {
       proxy_pass http://localhost:8000/;
       proxy_buffering off;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-Host $host;
       proxy_set_header X-Forwarded-Port $server_port;
       }

    }


Then, within directory /etc/nginx/sites-enabled delete the default link, and create a new link to myproj.conf:

sudo rm default

sudo ln -s /etc/nginx/sites-available/myproj.conf /etc/nginx/sites-enabled/

Now reboot the server or restart nginx with command "sudo service nginx restart"

Connecting to your server with a browser on port 80 should now show your INDI project.

The above serves port 80, to serve https with a certificate is more complicated. A bit too much to document here!
