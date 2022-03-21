import asyncio
import struct
from enum import Enum
from typing import Callable, Dict, Optional, Tuple, NamedTuple
import logging
import json
import random

from .exceptions import RequestTimedOutException


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
        MSG_HST = "MSG_HST"  # Request message history for group
        USR_LOGIN = "USR_LOGIN" # Request to veryify user credentials
        USR_ADD = "USR_ADD"  # Request to create a new user
        USR_LST = "USR_LST"  # Request a list of all usernames
        MSG_RBA = "MSG_RBA"  # Message read by all group members

    def __init__(self, header: UDPHeader, data: Optional[Dict] = None):
        """Initialize a chat message from header and data."""
        self.header = header
        self.data: Dict = {} if data is None else data
        self.type: Optional[UDPMessage.MessageType] = None
        if "type" in self.data:
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


class TimeoutRetransmissionProtocol(asyncio.Protocol):

    MAX_TIMEOUT = 5  # Max timeout (s). After this, the socket is closed.

    def __init__(self):
        """Initialize the protocol. At this stage, no transport has been created."""
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.future_responses: Dict[int, asyncio.Future] = {}
        self.bytes_sent: int = random.randrange(0, 10000)
        self.on_receive_message_listener: Optional[Callable[[UDPMessage], None]] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Transport has been initialized."""
        self.transport = transport

    def send_message(self,
                     data: Optional[Dict] = None,
                     msg: Optional[UDPMessage] = None,
                     addr: Optional[Address] = None,
                     verify_delay: float = 0.5,
                     on_response: Optional[Callable] = None) -> asyncio.Future:
        """Send a message to the server/client. Starts a timer to verify receipt."""
        if self.transport is None:
            raise ValueError("Cannot send message without transport.")
        if msg is None:
            if data is None:
                raise ValueError("Must specify message or data to send")
            msg = UDPMessage(UDPHeader(SEQN=self.bytes_sent, ACK=False, SYN=False), data=data)
        msg_bytes = msg.to_bytes()
        # Push the message onto the write buffer
        self.transport.sendto(msg_bytes, addr)
        # Verify the message:
        # 1. Create a future response to set when the verification succeeds
        future_response = asyncio.get_event_loop().create_future()
        # A bit cheeky: set the request message as an attribute on the response,
        # so the response handler can access the original request.
        future_response.request = msg  # type: ignore
        verify_coroutine = self.verify_message(
            msg, future_response, delay=verify_delay, addr=addr)
        # Start the verification task
        verify_task = asyncio.create_task(verify_coroutine)
        # Cancel the verification task when the response is returned
        future_response.add_done_callback(lambda f: verify_task.cancel())
        # Run the on_timed_out handler if the requests throws a RequestTimedOutException
        future_response.add_done_callback(
            lambda f: self.on_timed_out(addr) if isinstance(
                f.exception(), RequestTimedOutException) else None)
        # Add an optional user-specified response callback
        if on_response:
            future_response.add_done_callback(on_response)
        if self.future_responses.get(msg.header.SEQN):
            logging.warning("Request with this SEQN already esists. It's response may be lost.")
        self.future_responses[msg.header.SEQN] = future_response
        self.bytes_sent += len(msg_bytes)
        logging.debug(f"Send {msg} to {addr}")
        # Allows await send_message()
        return future_response

    async def verify_message(
            self,
            msg: UDPMessage,
            future_response: asyncio.Future,
            addr: Optional[Address] = None,
            delay: float = 0.5):
        """Asynchronously verify messages in the event loop."""
        if self.transport is None:
            return
        total_delay = 0
        while total_delay < self.MAX_TIMEOUT:
            msg_bytes = msg.to_bytes()
            actual_delay = min(delay, self.MAX_TIMEOUT-total_delay)
            await asyncio.sleep(actual_delay)
            total_delay += actual_delay
            # Send a message, but don't start a new verification task
            # (since this one is already running)
            logging.debug(f"Re-send {msg} (verification timed out after {delay:.1f}s)")
            self.transport.sendto(msg_bytes, addr)
            delay *= 2  # Wait for twice as long
        logging.error(f"Timed out after {total_delay:.1f}s, cancel request.")
        future_response.set_exception(RequestTimedOutException)

    def on_timed_out(self, addr: Optional[Address]) -> None:
        """Abstract on_timed_out method."""
        pass

    def datagram_received(self, data: bytes, addr: Address) -> bool:
        """Received a datagram from the server or client."""
        if self.transport is None:
            return False
        msg = UDPMessage.from_bytes(data)
        # Received an ack, try stop the timer
        if msg.header.ACK:
            # Only really relevant for the server protocol: when receiving
            # an message ACK from a client, the message should be marked as 'read'
            # or 'delivered'.
            if msg.data:
                uname = msg.data.get("username")
                mid = msg.data.get("MessageID")
                group = msg.data.get("group")
                if uname and mid is not None and group:
                    self.on_receive_ack(str(group), str(uname), int(mid))
                    # Notify listeners that an RBA message has come through
                    if self.on_receive_message_listener is not None:
                        self.on_receive_message_listener(msg)
            future_response = self.future_responses.get(msg.header.SEQN)
            # Stop running the timer task
            if future_response is not None:
                # Set the response - this will cancel the verification task
                # and call the optional response callback
                future_response.set_result(msg)
                # Remove the from the list of future responses
                del self.future_responses[msg.header.SEQN]
            return False
        if self.on_receive_message_listener is not None:
            self.on_receive_message_listener(msg)
        logging.debug("Received: %s" % msg)
        return True

    def set_receive_listener(self, listener: Callable[[UDPMessage], None]):
        """Set an external listener for incoming UDP messages."""
        self.on_receive_message_listener = listener

    def on_receive_ack(self, group: str, uname: str, mid: int) -> None:
        """Abstract method. Reimplemented in the server protocol."""
        pass
