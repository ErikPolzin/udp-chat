"""Terminal-based chat client, used in conjunction with a running ServerChatProtocol endpoint."""
import asyncio
from datetime import datetime
import sys
from typing import Callable, Dict, Optional, Set
import logging

from async_udp_server import UDPHeader, UDPMessage, Address, get_host_and_port
from exceptions import RequestTimedOutException


class ClientChatProtocol(asyncio.Protocol):
    """Client-side chat protocol.
    
    Responsible for sending chat messages to the server,
    and veryfing their arrival.
    """

    MAX_TIMEOUT = 5  # Max timeout (s). After this, the socket is closed.

    @classmethod
    async def create(cls, server_addr: Address):
        """Create a new ClientChatProtocol in the async event loop."""
        loop = asyncio.get_running_loop()
        on_con_lost = loop.create_future()

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: cls(on_con_lost),
            remote_addr=server_addr)
        return protocol

    def __init__(self, on_con_lost: asyncio.Future):
        """Initialize the protocol. At this stage, no transport has been created."""
        self.on_con_lost = on_con_lost
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.future_responses: Dict[int, asyncio.Future] = {}
        self.bytes_sent: int = 0
        self.on_receive_message_listener: Optional[Callable[[UDPMessage], None]] = None
        self.server_connected_listeners: Set[Callable[[], None]] = set()

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Connection made to the server.
        
        For UDP, this doesn't mean very much, since the protocol is connectionless,
        so this extended protocol  sends an additional SYN header to indicate
        a new connection.
        """
        self.transport = transport
        self.connect_to_server()

    def connect_to_server(self):
        """Send a connection message to the server."""
        connect_msg = UDPMessage(UDPHeader(SEQN=0, ACK=False, SYN=True))
        self.send_message(msg=connect_msg, on_response=self.connected_to_server)

    def connected_to_server(self, response: asyncio.Future):
        """Callback after the client has made a successful connection to the server."""
        if response.exception():
            logging.error("Error connecting to server")
        else:
            # Call the server connect listeners.
            for callb in self.server_connected_listeners:
                callb()
            logging.info("Connected to server!")

    def send_message(self,
                     data: Dict = None,
                     msg: UDPMessage = None,
                     on_response: Callable = None) -> None:
        """Send a message to the server. Starts a timer to verify receipt."""
        if msg is None:
            if data is None:
                raise ValueError("Must specify message or data to send")
            msg = UDPMessage(UDPHeader(SEQN=self.bytes_sent, ACK=False, SYN=False), data=data)
        msg_bytes = msg.to_bytes()
        # Push the message onto the write buffer
        self.transport.sendto(msg_bytes)
        # Verify the message:
        # 1. Create a future response to set when the verification succeeds
        future_response = asyncio.get_event_loop().create_future()
        # A bit cheeky: set the request message as an attribute on the response,
        # so the response handler can access the original request.
        future_response.request = msg
        verify_coroutine = self.verify_message(msg, future_response)
        # Start the verification task
        verify_task = asyncio.create_task(verify_coroutine)
        # Cancel the verification task when the response is returned
        future_response.add_done_callback(lambda f: verify_task.cancel())
        # Add an optional user-specified response callback
        if on_response:
            future_response.add_done_callback(on_response)
        self.future_responses[msg.header.SEQN] = future_response
        self.bytes_sent += len(msg_bytes)
        # Allows await send_message()
        return future_response

    async def verify_message(
            self, msg: UDPMessage, future_response: asyncio.Future, delay: float = 0.5):
        """Asynchronously verify messages in the event loop."""
        total_delay = 0
        while total_delay < self.MAX_TIMEOUT:
            msg_bytes = msg.to_bytes()
            actual_delay = min(delay, self.MAX_TIMEOUT-total_delay)
            await asyncio.sleep(actual_delay)
            total_delay += actual_delay
            # Send a message, but don't start a new verification task
            # (since this one is already running)
            logging.debug(f"Re-send {msg} (verification timed out after {delay:.1f}s)")
            self.transport.sendto(msg_bytes)
            delay *= 2  # Wait for twice as long
        logging.error(f"Timed out after {total_delay:.1f}s, cancel request.")
        future_response.set_exception(RequestTimedOutException)
        self.on_con_lost.set_result(True)

    def datagram_received(self, data: bytes, addr: Address):
        """Received a datagram from the server."""
        msg = UDPMessage.from_bytes(data)
        # Received an ack, try stop the timer
        if msg.header.ACK:
            future_response = self.future_responses.get(msg.header.SEQN)
            # Stop running the timer task
            if future_response is not None:
                # Set the response - this will cancel the verification task
                # and call the optional response callback
                future_response.set_result(msg)
                # Remove the from the list of future responses
                del self.future_responses[msg.header.SEQN]
            status = msg.data.get("status")
            if status != 200 and status is not None:
                logging.warning(f"Received error: {msg.data.get('error')} [{status}]")
            return
        if self.on_receive_message_listener is not None:
            self.on_receive_message_listener(msg)
        logging.debug("Received: %s" % msg)

    def error_received(self, exc):
        """Received an error from the server."""
        logging.error('Error received: %s' % exc)

    def connection_lost(self, exc):
        """Connection to server lost."""
        logging.warning("Connection lost")
        self.on_con_lost.set_result(True)

    def set_receive_listener(self, listener: Callable[[UDPMessage], None]):
        """Set an external listener for incoming UDP messages."""
        self.on_receive_message_listener = listener

    def add_server_connected_listener(self, listener: Callable[[], None]) -> None:
        """Add a callable to the set of connected listeners."""
        self.server_connected_listeners.add(listener)


async def ainput(string: str = None) -> str:
    """Await user input from standard input."""
    if string:
        await asyncio.get_event_loop().run_in_executor(
                None, lambda s=string: sys.stdout.write(s+' '))
    return str(await asyncio.get_event_loop().run_in_executor(
            None, sys.stdin.readline)).strip("\n")

async def main(server_addr: Address):
    """Run the client, sending typed messages from the terminal to the default chat room."""
    logging.info(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
    protocol: ClientChatProtocol = await ClientChatProtocol.create(server_addr)
    try:
        while True:
            text = await ainput()
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
                "username": "root"})
    finally:
        protocol.transport.close()


if __name__ == "__main__":
    server_addr = get_host_and_port(random_port=True)
    try:
        asyncio.run(main(server_addr))
    except KeyboardInterrupt:
        logging.info("Caught keyboard interrupt, exiting...")
        sys.exit(0)
