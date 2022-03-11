-----------------------------------------------------------------
        AYSNCHRONOUS UDP-BASED CHAT APPLICATION
-----------------------------------------------------------------

        How to set up and run the application.

-----------------------------------------------------------------
        1. Create a python virtual enviroment
-----------------------------------------------------------------

1. Run "make venv" to create the virtual enviroment.
2. Run "venv/bin/activate" to activate the virtual enviroment.

-----------------------------------------------------------------
        2. Starting the server
-----------------------------------------------------------------

On localhost
1. Run "make server" to start running the server.

On specified IP address
1. Run "make server (IP address) (port number)" to start running the server

-----------------------------------------------------------------
        3. Starting a client GUI
-----------------------------------------------------------------

In a new terminal:

Connect to a server on localhost
1. Run "make gui" to start the client GUI 

Connect to a server IP address 
1. Run "make gui (IP address) (port number)" to start the client GUI 

-----------------------------------------------------------------
        4. Starting a command line client
-----------------------------------------------------------------

### Must already have created an account ###

In a new terminal:

Connect to a server on localhost
1. Run "make cli" to start the client 

Connect to a server IP address 
1. Run "make cli (IP address) (port number)" to start the client GUI 

-----------------------------------------------------------------
        5. Delete the enviroment
-----------------------------------------------------------------

1. Run "make clean" to delete the virtual enviroment