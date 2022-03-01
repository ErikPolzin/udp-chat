"""Terminal-based chat client, used in conjunction with a running ServerChatProtocol endpoint."""
import asyncio
import sys
from typing import Callable, Dict, Optional

from async_udp_server import ChatHeader, ChatMessage, Address, get_host_and_port


class ClientChatProtocol(asyncio.Protocol):
    """Client-side chat protocol.
    
    Responsible for sending chat messages to the server,
    and veryfing their arrival.
    """

    MAX_TIMEOUT = 10  # Max timeout (s). After this, the socket is closed.

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
        self.verify_timers: Dict[int, asyncio.Task] = {}
        self.bytes_sent: int = 0
        self.on_receive_message_listener: Optional[Callable[[ChatMessage], None]] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Connection made to the server.
        
        For UDP, this doesn't mean very much, since the protocol is connectionless,
        so this extended protocol  sends an additional SYN header to indicate
        a new connection.
        """
        self.transport = transport
        connect_msg = ChatMessage(ChatHeader(SEQN=0, ACK=False, SYN=True))
        self.send_message(msg=connect_msg)

    def send_message(self,
                     data: Dict = None,
                     msg: ChatMessage = None,
                     verify_timeout=0.5,
                     resend=False) -> None:
        """Send a message to the server. Starts a timer to verify receipt."""
        if msg is None:
            if data is None:
                raise ValueError("Must specify message or data to send")
            msg = ChatMessage(ChatHeader(SEQN=self.bytes_sent, ACK=False, SYN=False), data=data)
        msg_bytes = msg.to_bytes()
        # Push the message onto the write buffer
        self.transport.sendto(msg_bytes)
        # Start the verify timer coroutine
        verify_coroutine = self.verify_message(verify_timeout, msg, resend=resend)
        self.verify_timers[self.bytes_sent] = asyncio.create_task(verify_coroutine)
        self.bytes_sent += len(msg_bytes)

    def total_delay(self, delay: float) -> float:
        """Estimate the total time spent attempting to reach the server."""
        tot_time = 0
        prev_delay = 0.5
        while prev_delay <= delay:
            tot_time += prev_delay
            prev_delay *= 2
        return tot_time

    async def verify_message(self, delay: float, msg: ChatMessage, resend=False):
        """Asynchronously verify messages in the event loop."""
        if self.total_delay(delay) >= self.MAX_TIMEOUT:
            print("Server didn't respond after MAX_TIMEOUT, cancel ")
            return
        print('Send:' if not resend else "Resend:", msg)
        await asyncio.sleep(delay)
        # Double the delay for the next resend
        self.send_message(None, msg, delay*2, resend=True)

    def datagram_received(self, data: bytes, addr: Address):
        """Received a datagram from the server."""
        msg = ChatMessage.from_bytes(data)
        # Received an ack, try stop the timer
        if msg.header.ACK:
            timerTask = self.verify_timers.get(msg.header.SEQN)
            if timerTask is not None:
                timerTask.cancel()
            status = msg.data.get("status")
            if status != 200:
                print(f"Received error: {msg.data.get('error')} [{status}]")
            print(f"Verified msg {msg.header.SEQN}")
            return
        if self.on_receive_message_listener is not None:
            self.on_receive_message_listener(msg)
        print("Received:", msg)

    def error_received(self, exc):
        """Received an error from the server."""
        print('Error received:', exc)

    def connection_lost(self, exc):
        """Connection to server lost."""
        print("Connection closed")
        self.on_con_lost.set_result(True)

    def set_receive_listener(self, listener: Callable[[ChatMessage], None]):
        """Set an external listener for incoming chat messages."""
        self.on_receive_message_listener = listener


async def ainput(string: str = None) -> str:
    """Await user input from standard input."""
    if string:
        await asyncio.get_event_loop().run_in_executor(
                None, lambda s=string: sys.stdout.write(s+' '))
    return str(await asyncio.get_event_loop().run_in_executor(
            None, sys.stdin.readline)).strip("\n")

async def main(server_addr: Address):
    """Run the client, sending typed messages from the terminal to the default chat room."""
    print(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
    protocol: ClientChatProtocol = await ClientChatProtocol.create(server_addr)
    try:
        while True:
            text = await ainput()
            # Extract message type from input
            mtype = ChatMessage.MessageType.CHT
            group = "default"
            if ":" in text:
                mtype_txt, text = text.split(":")
                mtype = ChatMessage.MessageType(mtype_txt)
            # Extract group name from input
            if "GRP=" in text:
                text, group = text.split("GRP=")
            protocol.send_message({"type": mtype.value, "text": text, "group": group})
    finally:
        protocol.transport.close()


if __name__ == "__main__":
    server_addr = get_host_and_port()
    try:
        asyncio.run(main(server_addr))
    except KeyboardInterrupt:
        print("aught keyboard interrupt, exiting...")
        sys.exit(0)
