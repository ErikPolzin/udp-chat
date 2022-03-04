"""Asynchronous UDP server implementation for a group chat API using websockets."""
import asyncio
import json
from multiprocessing.sharedctypes import Value
import struct
import sys
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, NamedTuple, Union
from exceptions import ItemAlreadyExistsException, ItemNotFoundException

from chat_database_controller import DatabaseController

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
        MSG_HST = "MSG_HST"

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
            grp = self.data.get("group", "default")
            if self.type == UDPMessage.MessageType.CHT:
                return f"<UDPMessage {self.header.SEQN}: '{self.data.get('text')}', grp={grp}>"
            if self.type == UDPMessage.MessageType.GRP_SUB:
                return f"<UDPMessage {self.header.SEQN}: GRP_SUB grp={grp}>"
            if self.type == UDPMessage.MessageType.GRP_ADD:
                return f"<UDPMessage {self.header.SEQN}: GRP_ADD grp={grp}>"
        return f"<UDPMessage {self.header.SEQN}: EMPTY>"

    @classmethod
    def from_bytes(cls, data: bytes) -> 'UDPMessage':
        """Initialize from a UDP packet."""
        header = UDPHeader.from_bytes(data)
        mdata = json.loads(data[HEADER_SIZE:]) if data[HEADER_SIZE:] else None
        return UDPMessage(header, mdata)

    def to_bytes(self) -> bytes:
        """Serialize a chat message."""
        return self.header.to_bytes() + json.dumps(self.data).encode()


class InMemoryGroupLayer(Dict[str, Set[Address]]):
    """Registers, removed and sends messages to groups."""

    def __init__(self, transport: asyncio.DatagramTransport):
        """Initialize a memory group layer."""
        self.transport = transport
        self["default"] = set()

    def group_add(self, group: str, addr: Address) -> None:
        """Register a channel in a new group."""
        if group in self:
            raise ItemAlreadyExistsException(group)
        self[group] = {addr}
        print(f"{addr[0]}:{addr[1]} created new group: '{group}'")

    def group_sub(self, group: str, addr: Address) -> None:
        """Register a channel in an existing group."""
        if group not in self:
            raise ItemNotFoundException(group)
        self.setdefault(group, set()).add(addr)
        print(f"Subscribe {addr[0]}:{addr[1]} to group '{group}'")

    def group_send(self, group: str, msg: UDPMessage) -> None:
        """Send a message to all addresses in a group."""
        print(f"Send {msg} to group '{group}'")
        for addr in self.get(group, set()):
            self.transport.sendto(msg.to_bytes(), addr)

    def deregister_address(self, addr: Address) -> None:
        """De-register address from all groups."""
        for addresses in self.values():
            addresses.discard(addr)


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
        self.db_controller = DatabaseController("udpchat", "root")
        self.group_layer = InMemoryGroupLayer(transport)

    def client_connection_made(self, addr: Address) -> None:
        """Created a connection to a remote socket."""
        self.group_layer.group_sub("default", addr)

    def client_connection_terminated(self, addr: Address) -> None:
        """Signalled to close the connection to the server."""
        self.group_layer.deregister_address(addr)

    def datagram_received(self, data: bytes, addr: Address) -> None:
        """Received a datagram from the chat's socket."""
        if self.transport is None:
            return
        msg = UDPMessage.from_bytes(data)
        if msg.header.SYN:
            self.client_connection_made(addr)
        if msg.header.FIN:
            self.client_connection_terminated(addr)
        print('Received %s from %s' % (msg, addr))
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
        # Message is a chat message, send it to the associated group
        if mtype == UDPMessage.MessageType.CHT:
            text = msg.data.get("text")
            try:
                self.db_controller.new_message(group_name, user_name, text)
            except Exception as e:
                return 500, None, f"Unable to save message: {e}"
            self.group_layer.group_send(group_name, msg)
            return 200, None, None
        # Message is a group add, try create a new group
        elif mtype == UDPMessage.MessageType.GRP_ADD:
            try:
                self.db_controller.new_group(group_name, user_name)
                self.group_layer.group_add(group_name, addr)
                return 200, None, None
            except ItemAlreadyExistsException:
                return 400, None, "Group with this name already exists"
            except Exception as e:
                return 500, None, f"Unable to create group: {e}"
        # Message is a group subscription, try sub to group
        elif mtype == UDPMessage.MessageType.GRP_SUB:
            try:
                self.group_layer.group_sub(group_name, addr)
                return 200, None, None
            except ItemNotFoundException:
                return 400, None, "Group with this name already exists"
        elif mtype == UDPMessage.MessageType.MSG_HST:
            message_history = self.db_controller.message_history(group_name)
            # Message dates have to be converted to strings for JSON
            [m.update({"Date_Sent": m["Date_Sent"].isoformat()}) for m in message_history]
            return 200, message_history, None
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
    host, port = get_host_and_port()
    print(f"Starting UDP server at {host}:{port}...")

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
        print("aught keyboard interrupt, exiting...")
        sys.exit(0)