# Asynchronous UDP-based chat app

## Running the server

To start the server, run
```bash
python3 -m udp_chat.server
```

Provide optional command-line arguments `HOST, PORT`, i.e.:
```bash
python3 -m udp_chat.server 192.168.10.109 4999
```


## Creating a text-based client

To create a client connection in the terminal window, run
```bash
python3 -m udp_chat.client
```

Type a message into the console, and see it broadcast to other clients in the default chat group.


## Running a GUI client

Ensure PyQT5 is installed. Then run (from the root directory):
```bash
python3 -m udp_chat.gui_client
```