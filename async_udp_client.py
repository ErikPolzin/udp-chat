"""Terminal-based chat client, used in conjunction with a running ServerChatProtocol endpoint."""
import asyncio
import sys
from typing import Dict, Optional

from async_udp_server import ChatHeader, ChatMessage


class ClientChatProtocol(asyncio.Protocol):
    """Client-side chat protocol.
    
    Responsible for sending chat messages to the server,
    and veryfing their arrival.
    """

    MAX_TIMEOUT = 10  # Max timeout (s). After this, the socket is closed.

    def __init__(self, on_con_lost: asyncio.Future):
        """Initialize the protocol. At this stage, no transport has been created."""
        self.on_con_lost = on_con_lost
        self.transport: Optional[asyncio.DatagramTransport] = None
        self.verify_timers: Dict[int, asyncio.Task] = {}
        self.bytes_sent: int = 0

    def connection_made(self, transport: asyncio.DatagramTransport):
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

    async def verify_message(self, delay: int, msg: ChatMessage, resend=False):
        """Asynchronously verify messages in the event loop."""
        print('Send:' if not resend else "Resend:", msg)
        await asyncio.sleep(delay)
        # Double the delay for the next resend
        self.send_message(None, msg, delay*2, resend=True)

    def datagram_received(self, data, addr):
        """Received a datagram from the server."""
        msg = ChatMessage.from_bytes(data)
        # Received an ack, try stop the timer
        if msg.header.ACK:
            timerTask = self.verify_timers.get(msg.header.SEQN)
            if timerTask is not None:
                timerTask.cancel()
            print(f"Verified msg {msg.header.SEQN}")
            return
        print("Received:", msg)

    def error_received(self, exc):
        """Received an error from the server."""
        print('Error received:', exc)

    def connection_lost(self, exc):
        """Connection to server lost."""
        print("Connection closed")
        self.on_con_lost.set_result(True)


async def ainput(string: str = None) -> str:
    """Await user input from standard input."""
    if string:
        await asyncio.get_event_loop().run_in_executor(
                None, lambda s=string: sys.stdout.write(s+' '))
    return str(await asyncio.get_event_loop().run_in_executor(
            None, sys.stdin.readline)).strip("\n")

async def main():
    """Run the client, sending typed messages from the terminal to the default chat room."""
    # Get a reference to the event loop as we plan to use
    # low-level APIs.
    loop = asyncio.get_running_loop()

    on_con_lost = loop.create_future()

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: ClientChatProtocol(on_con_lost),
        remote_addr=('127.0.0.1', 5000))

    try:
        while True:
            text = await ainput()
            protocol.send_message({"type": ChatMessage.CHT, "text": text, "group": "default"})
    finally:
        transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("aught keyboard interrupt, exiting...")