"""Asynchronous UDP server implementation for a group chat API using websockets."""
import asyncio
import json
import struct
import sys
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, NamedTuple, Union
import logging
from datetime import datetime

from exceptions import ItemAlreadyExistsException, ItemNotFoundException
from db_sqlite import DatabaseController

# Constants
HEADER_FORMAT: str = "!i???"
HEADER_STRUCT: struct.Struct = struct.Struct(HEADER_FORMAT)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

Address = Tuple[str, int]


class UDPHeader(NamedTuple):
    """Additional UDP packet data, stored in binary."""

    SEQN: int = 0
    ACK: bool = False
    SYN: bool = False
    FIN: bool = False

    @classmethod
    def from_bytes(cls, data: bytes) -> 'UDPHeader':
        """Create a UDP Header from bytes."""
        return UDPHeader._make(HEADER_STRUCT.unpack(data[:HEADER_SIZE]))

    def to_bytes(self) -> bytes:
        """Serialize a UDP header."""
        return HEADER_STRUCT.pack(*self)


class UDPMessage(object):
    """Represents a message sent to the server, originally as a UDP packet."""

    class MessageType(Enum):
        """Enumerate all the allowed message types."""

        CHT = "CHT"  # Chat message
        GRP_SUB = "GRP_SUB"  # Request to subscribe to an existing group
        GRP_ADD = "GRP_ADD"  # Request to create a new group
        GRP_HST = "GRP_HST"  # Request group history
        MSG_HST = "MSG_HST" #Request message history for group
        USR_LOGIN = "USR_LOGIN" #Request to veryify user credentials
        USR_ADD = "USR_ADD" #Request to create a new user

    def __init__(self, header: UDPHeader, data: Optional[dict] = None):
        """Initialize a chat message from header and data."""
        self.header = header
        self.data = data
        self.type: Optional[UDPMessage.MessageType] = None
        if self.data and "type" in data:
            try:
                self.type = self.MessageType(self.data["type"])
            except ValueError:
                self.type = None

    def __str__(self) -> str:
        """Stringify a chat message."""
        if self.header.ACK:
            return f"<UDPMessage {self.header.SEQN}: ACK>"
        if self.header.SYN:
            return f"<UDPMessage {self.header.SEQN}: SYN>"
        if self.header.FIN:
            return f"<UDPMessage {self.header.SEQN}: FIN>"
        if self.data and self.type:
            return f"<UDPMessage {self.header.SEQN}: {self.type} grp={self.data.get('group')}>"
        return f"<UDPMessage {self.header.SEQN}: {self.type}, data={self.data}>"

    @classmethod
    def from_bytes(cls, data: bytes) -> 'UDPMessage':
        """Initialize from a UDP packet."""
        header = UDPHeader.from_bytes(data)
        mdata = json.loads(data[HEADER_SIZE:]) if data[HEADER_SIZE:] else None
        return UDPMessage(header, mdata)

    def to_bytes(self) -> bytes:
        """Serialize a chat message."""
        return self.header.to_bytes() + json.dumps(self.data).encode()


class SqliteGroupLayer(object):
    """Registers, removed and sends messages to groups."""

    def __init__(self, transport: asyncio.DatagramTransport, db_controller: DatabaseController):
        """Initialize a memory group layer."""
        self.transport = transport
        self.db_controller = db_controller

    def group_add(self, group: str, user_name: str) -> None:
        """Register a channel in a new group."""
        self.db_controller.new_group(group, user_name)
        logging.info(f"{user_name} created new group: '{group}'")

    def group_sub(self, group: str, username: str) -> None:
        """Register a channel in an existing group."""
        self.db_controller.new_member(username, group)
        logging.info(f"Subscribe {username} to group '{group}'")

    def group_send(self, group: str, msg: UDPMessage) -> None:
        """Send a message to all addresses in a group."""
        logging.info(f"Send {msg} to group '{group}'")
        for addr in self.db_controller.get_addresses_for_group(group):
            self.transport.sendto(msg.to_bytes(), addr)


class ServerChatProtocol(asyncio.Protocol):
    """Server-side chat protocol.
    
    The server is responsible for sending ACK messages back to senders,
    so they can verify their UDP packets have reached the server (similar
    to the way TCP acknowledges its packets).

    It is also responsible for broadcasting group messages to participants.
    """

    transport: Optional[asyncio.DatagramTransport]

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Created a connection to the local socket."""
        self.transport = transport
        self.db_controller = DatabaseController()
        self.group_layer = SqliteGroupLayer(transport, self.db_controller)

    def client_connection_made(self, addr: Address) -> None:
        """Created a connection to a remote socket."""
        pass

    def client_connection_terminated(self, addr: Address) -> None:
        """Signalled to close the connection to the server."""
        pass

    def datagram_received(self, data: bytes, addr: Address) -> None:
        """Received a datagram from the chat's socket."""
        if self.transport is None:
            return
        msg = UDPMessage.from_bytes(data)
        if msg.header.SYN:
            self.client_connection_made(addr)
        if msg.header.FIN:
            self.client_connection_terminated(addr)
        logging.debug('Received %s from %s' % (msg, addr))
        ack_msg = UDPMessage(UDPHeader(msg.header.SEQN, ACK=True, SYN=False), {})
        # Determine the message type and process accordingly
        if msg.data and msg.type:
            status, data, error = self.message_received(msg, addr)
            ack_msg.data["status"] = status
            ack_msg.data["error"] = error
            ack_msg.data["response"] = data
        # Echo an acknowledgement to the sender, with the same sequence number.
        self.transport.sendto(ack_msg.to_bytes(), addr)

    def message_received(
            self, msg: UDPMessage, addr: Address
        ) -> Tuple[int, Optional[Union[List, Dict]], Optional[str]]:
        """Received a message with an associated type. Usually called after datagram_received()."""
        mtype = msg.type
        group_name = msg.data.get("group", "default")
        user_name = msg.data.get("username", "root")
        password = msg.data.get("password", "default")
        # Message is a chat message, send it to the associated group
        if mtype == UDPMessage.MessageType.CHT:
            text = msg.data.get("text")
            time_sent = datetime.now()
            if "time_sent" in msg.data:
                time_sent = datetime.fromisoformat(msg.data["time_sent"])
            try:
                self.db_controller.new_message(group_name, user_name, text, time_sent)
            except Exception as e:
                return 500, None, f"Unable to save message: {e}"
            self.group_layer.group_send(group_name, msg)
            return 200, None, None
        # Message is a group add, try create a new group
        elif mtype == UDPMessage.MessageType.GRP_ADD:
            try:
                self.group_layer.group_add(group_name, addr)
                logging.info(f"Created new group '{group_name}'")
                return 200, {"group": group_name}, None
            except ItemAlreadyExistsException:
                return 400, None, "Group with this name already exists"
            except Exception as e:
                return 500, None, f"Unable to create group: {e}"
        elif mtype == UDPMessage.MessageType.GRP_HST:
            group_history = list(self.db_controller.group_history(user_name))
            return 200, group_history, None
        # Message is a group subscription, try sub to group
        elif mtype == UDPMessage.MessageType.GRP_SUB:
            try:
                self.group_layer.group_sub(group_name, user_name)
                return 200, None, None
            except ItemNotFoundException:
                return 400, None, "Group with this name already exists"
        elif mtype == UDPMessage.MessageType.MSG_HST:
            message_history = list(self.db_controller.message_history(group_name))
            return 200, message_history, None
        elif mtype == UDPMessage.MessageType.USR_LOGIN:
            try:
                cred_valid = self.db_controller.user_login(user_name, password, addr)
            except ItemNotFoundException:
                return 400, None, "Account doesn't exist."
            return 200, {"credentials_valid": cred_valid, "username": user_name}, None
        elif mtype == UDPMessage.MessageType.USR_ADD:
            straddr = f"{addr[0]}:{addr[1]}"
            created = self.db_controller.new_user(user_name, password, straddr)
            # Add the new user to the 'default' group
            if created:
                self.group_layer.group_sub("default", user_name)
            return 200, {"created_user": created}, None
        else:
            return 400, None, f"Unrecognised message type '{mtype}'"


def get_host_and_port() -> Address:
    """Get the host and port from system args."""
    if len(sys.argv) == 3:
        host, port = sys.argv[1], int(sys.argv[2])
    elif len(sys.argv) == 2:
        host, port = sys.argv[1], 5000
    else:
        host, port = '127.0.0.1', 5000
    return (host, port)

async def main():
    logging.basicConfig(level=logging.DEBUG)
    host, port = get_host_and_port()
    logging.info(f"Starting UDP server at {host}:{port}...")

    loop = asyncio.get_event_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: ServerChatProtocol(),
        local_addr=(host, port))

    try:
        await asyncio.sleep(3600)
    finally:
        transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("aught keyboard interrupt, exiting...")
        sys.exit(0)