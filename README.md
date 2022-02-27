# Asynchronous UDP-based chat app

## Running the server

To start the server, run
```bash
python3 async_udp_server.py
```

Provide optional command-line arguments `HOST, PORT`, i.e.:
```bash
python3 async_udp_server.py 192.168.10.109 4999
```


## Creating a text-based client

To create a client connection in the terminal window, run
```bash
python3 async_udp_client.py
```

Type a message into the console, and see it broadcast to other clients in the default chat group.