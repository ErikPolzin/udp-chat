"""Terminal-based chat client, used in conjunction with a running ServerChatProtocol endpoint."""
import asyncio
from datetime import datetime
import sys
from typing import Callable, Optional, Set
import logging
from getpass import getpass

from protocol import TimeoutRetransmissionProtocol, UDPHeader, UDPMessage, Address
from async_udp_server import get_host_and_port


class ClientChatProtocol(TimeoutRetransmissionProtocol):
    """Client-side chat protocol.
    
    Responsible for sending chat messages to the server,
    and veryfing their arrival.
    """

    @classmethod
    async def create(cls, server_addr: Address, uname: Optional[str] = None) -> 'ClientChatProtocol':
        """Create a new ClientChatProtocol in the async event loop."""
        loop = asyncio.get_running_loop()
        on_con_lost = loop.create_future()

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: cls(on_con_lost, uname),
            remote_addr=server_addr)
        return protocol

    def __init__(self, on_con_lost: asyncio.Future, uname: Optional[str] = None):
        """Initialize the protocol. At this stage, no transport has been created."""
        super().__init__()
        self.on_con_lost = on_con_lost
        self.username = uname
        self.server_connected_listeners: Set[Callable[[], None]] = set()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Connection made to the server.
        
        For UDP, this doesn't mean very much, since the protocol is connectionless,
        so this extended protocol  sends an additional SYN header to indicate
        a new connection.
        """
        self.transport = transport
        self.connect_to_server()

    def connect_to_server(self) -> None:
        """Send a connection message to the server."""
        data = {"username": self.username}
        connect_msg = UDPMessage(UDPHeader(SEQN=0, ACK=False, SYN=True), data)
        self.send_message(msg=connect_msg, on_response=self.connected_to_server)

    def connected_to_server(self, response: asyncio.Future) -> None:
        """Callback after the client has made a successful connection to the server."""
        if response.exception():
            logging.error("Error connecting to server")
        else:
            # Call the server connect listeners.
            for callb in self.server_connected_listeners:
                callb()
            logging.info("Connected to server!")

    def datagram_received(self, data: bytes, addr: Address) -> bool:
        """Received a datagram from the server.
        
        If the client receives a chat message, it must acknowledge it with the server.
        """
        if super().datagram_received(data, addr):
            if not self.transport:
                return False
            msg = UDPMessage.from_bytes(data)
            if msg.type == UDPMessage.MessageType.CHT and msg.data:
                # Send an ack to the server, echoing data back
                ack_data = {
                    "MessageID": msg.data.get("MessageID"),
                    "group": msg.data.get("group"),
                    "username": self.username,
                }
                ack_msg = UDPMessage(UDPHeader(msg.header.SEQN, ACK=True), ack_data)
                self.transport.sendto(ack_msg.to_bytes(), addr)
            # Client received confirmation that a message was read by all members
            if msg.type in (UDPMessage.MessageType.MSG_RBA, UDPMessage.MessageType.GRP_ADD):
                # Acknowledge the client has received this packet
                ack_msg = UDPMessage(UDPHeader(msg.header.SEQN, ACK=True), {})
                self.transport.sendto(ack_msg.to_bytes(), addr)
            return True
        return False

    def add_server_connected_listener(self, listener: Callable[[], None]) -> None:
        """Add a callable to the set of connected listeners."""
        self.server_connected_listeners.add(listener)

    def on_timed_out(self, addr: Optional[Address]) -> None:
        """Set the on_con_lost result."""
        self.on_con_lost.set_result(True)

    def error_received(self, exc):
        """Received an error from the server or client."""
        logging.error('Error received: %s' % exc)

    def connection_lost(self, exc):
        """Connection to server/client lost."""
        logging.warning("Connection lost")
        self.on_con_lost.set_result(True)


def cli_receive_message(msg: UDPMessage) -> None:
    """Cli received a message, print it to the terminal."""
    if msg.type == msg.MessageType.CHT and msg.data:
        group = msg.data.get("group", "<No group>")
        fromuser = msg.data.get("username", "anonymous")
        text = msg.data.get("text", "-")
        print(f"\r{fromuser}@{group}: {text}")
        print("Type a message: ", end="")


async def ainput(prompt: str = '') -> str:
    """Await user input from standard input."""
    sys.stdout.write(prompt)
    return str(await asyncio.get_event_loop().run_in_executor(
            None, sys.stdin.readline)).strip("\n")


async def wait_for_command_then_send(protocol: ClientChatProtocol):
    """Wait for user to type a line, then send it to the server through a protocol."""
    # Wait for user to successfully log in
    while True:
        username = input("Username: ")
        password = getpass()
        resp = await protocol.send_message({
            "type": "USR_LOGIN",
            "username": username,
            "password": password,
        })
        if resp.data.get("status") == 200:
            protocol.username = username
            protocol.set_receive_listener(cli_receive_message)
            print("Logged in!")
            break
        print("Error:", resp.data.get("error"))
    while True:
        text = await ainput("Type a message: ")
        # Extract message type from input
        mtype = UDPMessage.MessageType.CHT
        group = "default"
        if ":" in text:
            mtype_txt, text = text.split(":")
            mtype = UDPMessage.MessageType(mtype_txt)
        # Extract group name from input
        if "GRP=" in text:
            text, group = text.split("GRP=")
        protocol.send_message({
            "type": mtype.value,
            "text": text, 
            "group": group,
            "time_sent": datetime.now().isoformat(),
            "username": username})


def main(server_addr: Address):
    """Run the client, sending typed messages from the terminal to the default chat room."""
    logging.info(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
    loop = asyncio.get_event_loop()
    protocol = loop.run_until_complete(ClientChatProtocol.create(server_addr, None))
    try:
        loop.run_until_complete(wait_for_command_then_send(protocol))
    except KeyboardInterrupt:
        print("Caught keyboard interrupt")
    finally:
        if protocol.transport:
            print("Sending FIN to close connection...")
            # Send a FIN message to the server.
            fin_msg = UDPMessage(UDPHeader(0, FIN=True), {})
            loop.run_until_complete(protocol.send_message(msg=fin_msg, addr=server_addr))
            protocol.transport.close()
            print("Closed transport.")


if __name__ == "__main__":
    server_addr = get_host_and_port()
    main(server_addr)
