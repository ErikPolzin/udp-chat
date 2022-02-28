"""Asynchronous UDP server implementation for a group chat API using websockets."""
import asyncio
import json
import random
import struct
import sys
from typing import Optional, Tuple, NamedTuple

# Constants
HEADER_FORMAT: str = "!i??"
HEADER_STRUCT: struct.Struct = struct.Struct(HEADER_FORMAT)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

Address = Tuple[str, int]


class ChatHeader(NamedTuple):
    """Additional UDP packet data, stored in binary."""

    SEQN: int = 0
    ACK: bool = False
    SYN: bool = False

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ChatHeader':
        """Create a UDP Header from bytes."""
        return ChatHeader._make(HEADER_STRUCT.unpack(data[:HEADER_SIZE]))

    def to_bytes(self) -> bytes:
        """Serialize a UDP header."""
        return HEADER_STRUCT.pack(*self)


class ChatMessage(object):
    """Represents a message sent to the server, originally as a UDP packet."""

    # Chat message types
    CON = "CON"
    CHT = "CHT"

    def __init__(self, header: ChatHeader, data: Optional[dict] = None):
        """Initialize a chat message from header and data."""
        self.header = header
        self.data = data

    def __str__(self) -> str:
        """Stringify a chat message."""
        if self.header.ACK:
            return f"<ChatMessage {self.header.SEQN}: ACK>"
        if self.header.SYN:
            return f"<ChatMessage {self.header.SEQN}: SYN>"
        if self.data and "type" in self.data:
            if self.data["type"] == ChatMessage.CHT:
                return f"<ChatMessage {self.header.SEQN}: '{self.data.get('text')}'>"
        return f"<ChatMessage {self.header.SEQN}: EMPTY>"

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ChatMessage':
        """Initialize from a UDP packet."""
        header = ChatHeader.from_bytes(data)
        mdata = json.loads(data[HEADER_SIZE:]) if data[HEADER_SIZE:] else None
        return ChatMessage(header, mdata)

    def to_bytes(self) -> bytes:
        """Serialize a chat message."""
        return self.header.to_bytes() + json.dumps(self.data).encode()


class InMemoryGroupLayer(dict):
    """Registers, removed and sends messages to groups."""

    def __init__(self, transport: asyncio.DatagramTransport):
        """Initialize a memory group layer."""
        self.transport = transport
        self["default"] = set()

    def group_add(self, group: str, addr: Address) -> None:
        """Register a channel in a (potentially) new group."""
        self.setdefault(group, set()).add(addr)

    def group_send(self, group: str, msg: ChatMessage) -> None:
        """Send a message to all addresses in a group."""
        for addr in self.get(group, set()):
            self.transport.sendto(msg.to_bytes(), addr)


class ServerChatProtocol(asyncio.Protocol):
    """Server-side chat protocol.
    
    The server is responsible for sending ACK messages back to senders,
    so they can verify their UDP packets have reached the server (similar
    to the way TCP acknowledges its packets).

    It is also responsible for broadcasting group messages to participants.
    """

    transport: Optional[asyncio.DatagramTransport]

    def connection_made(self, transport: asyncio.DatagramTransport):
        """Created a connection to the local socket."""
        self.transport = transport
        self.group_layer = InMemoryGroupLayer(transport)

    def client_connection_made(self, addr: Address):
        """Created a connection to a remote socket."""
        self.group_layer.group_add("default", addr)

    def datagram_received(self, data: bytes, addr: Address):
        """Received a datagram from the chat's socket."""
        if self.transport is None:
            return
        msg = ChatMessage.from_bytes(data)
        if msg.header.SYN:
            self.client_connection_made(addr)
        print('Received %s from %s' % (msg, addr))
        # Echo an acknowledgement to the sender, with the same sequence number.
        ack_header = ChatHeader(msg.header.SEQN, ACK=True, SYN=False)
        self.transport.sendto(ack_header.to_bytes(), addr)
        # Send the message to the group, if applicable.
        if msg.data and msg.data.get("type") == ChatMessage.CHT:
            group_name = msg.data.get("group", "default")
            self.group_layer.group_send(group_name, msg)

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
        sys.exit(1)