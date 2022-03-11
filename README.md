-----------------------------------------------------------------
        AYSNCHRONOUS UDP-BASED CHAT APPLICATION
-----------------------------------------------------------------

        How to set up and run the application.

-----------------------------------------------------------------
        1. Create a python virtual enviroment
-----------------------------------------------------------------

1. Run "make venv" to create the virtual enviroment.
2. Run "source venv/bin/activate" to activate the virtual enviroment.

or 

1. Run "pip install -e ."

-----------------------------------------------------------------
        2. Starting the server
-----------------------------------------------------------------

On localhost
1. Run "python3 -m udp_chat.server" to start running the server. 

On specified IP address
1. Run "python3 -m udp_chat.server (IP address) (port number)" to start running the server

-----------------------------------------------------------------
        3. Starting a client GUI
-----------------------------------------------------------------

In a new terminal:

Connect to a server on localhost
1. Run "python3 -m udp_chat.gui_client" to start the client GUI 

Connect to a server IP address 
1. Run "python3 -m udp_chat.gui_client (IP address) (port number)" to start the client GUI

-----------------------------------------------------------------
        4. Starting a command line client
-----------------------------------------------------------------

### Must already have created an account ###

In a new terminal:

Connect to a server on localhost
1. Run "python3 -m udp_chat.client" to start the client 

Connect to a server IP address 
1. Run "python3 -m udp_chat.client (IP address) (port number)" to start the client GUI 

-----------------------------------------------------------------
        5. Delete the enviroment
-----------------------------------------------------------------

1. Run "make clean" to delete the virtual enviroment