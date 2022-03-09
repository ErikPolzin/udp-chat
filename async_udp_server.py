"""Asynchronous UDP server implementation for a group chat API using websockets."""
import asyncio
import sys
from typing import Dict, List, Optional, Tuple, Union
import logging
from datetime import datetime
import random

from protocol import TimeoutRetransmissionProtocol, UDPHeader, UDPMessage, Address
from exceptions import ItemAlreadyExistsException, ItemNotFoundException
from db_sqlite import DatabaseController


class SqliteGroupLayer(object):
    """Registers, removed and sends messages to groups."""

    def __init__(self, protocol: TimeoutRetransmissionProtocol, db_controller: DatabaseController):
        """Initialize a memory group layer."""
        self.protocol = protocol
        self.db_controller = db_controller

    def group_add(self, group: str, user_name: str, members: List[str]) -> None:
        """Register a channel in a new group."""
        self.db_controller.new_group(group, user_name)
        logging.info(f"{user_name} created new group: '{group}'")
        # Extremely inefficient but let's keep it simple
        for mname in members:
            self.group_sub(group, mname)

    def group_sub(self, group: str, username: str) -> None:
        """Register a channel in an existing group."""
        self.db_controller.new_member(username, group)
        logging.info(f"Subscribe {username} to group '{group}'")

    def group_send(self, group: str, msg: UDPMessage) -> None:
        """Send a message to all addresses in a group."""
        logging.info(f"Send {msg} to group '{group}'")
        for addr in self.db_controller.get_addresses_for_group(group):
            # Send a message with a really long verification timeout.
            # Don't want to double send messages unnecessarily.
            self.protocol.send_message(msg=msg, addr=addr, verify_delay=2)
            # Modify the header so it doesn't have the same SEQN!
            # Otherwise multiple messages will be sent with the same SEQN
            msg.header = UDPHeader(SEQN=self.protocol.bytes_sent)


class ServerChatProtocol(TimeoutRetransmissionProtocol):
    """Server-side chat protocol.
    
    The server is responsible for sending ACK messages back to senders,
    so they can verify their UDP packets have reached the server (similar
    to the way TCP acknowledges its packets).

    It is also responsible for broadcasting group messages to participants.
    """

    transport: Optional[asyncio.DatagramTransport]

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """Created a connection to the local socket."""
        super().connection_made(transport)
        self.db_controller = DatabaseController()
        self.group_layer = SqliteGroupLayer(self, self.db_controller)

    def client_connection_made(self, addr: Address, uname: Optional[str]) -> None:
        """Created a connection to a remote socket."""
        # Client connected without a username, this is acceptable
        if not uname:
            return
        try:
            with self.db_controller.connection() as c:
                self.db_controller.update_user_address(c, uname, addr)
        except Exception:
            pass

    def client_connection_terminated(self, addr: Address) -> None:
        """Signalled to close the connection to the server."""
        pass

    def datagram_received(self, data: bytes, addr: Address) -> bool:
        """Received a datagram from the chat's socket."""
        if super().datagram_received(data, addr) is False:
            return False
        # Mimic 20% of UDP packets not arriving
        if random.random() < 0.2 or self.transport is None:
            return False
        msg = UDPMessage.from_bytes(data)
        if msg.header.SYN:
            username = msg.data.get("username") if msg.data else None
            self.client_connection_made(addr, username)
        if msg.header.FIN:
            self.client_connection_terminated(addr)
        ack_msg = UDPMessage(UDPHeader(msg.header.SEQN, ACK=True, SYN=False), {})
        assert ack_msg.data is not None  # Keep mypy happy
        # Determine the message type and process accordingly
        if msg.data and msg.type:
            status, rdata, error = self.message_received(msg, addr)
            ack_msg.data["status"] = status
            ack_msg.data["error"] = error
            ack_msg.data["response"] = rdata
        # Echo an acknowledgement to the sender, with the same sequence number.
        self.transport.sendto(ack_msg.to_bytes(), addr)
        return True

    def message_received(
            self, msg: UDPMessage, addr: Address
        ) -> Tuple[int, Optional[Union[List, Dict]], Optional[str]]:
        """Received a message with an associated type. Usually called after datagram_received()."""
        assert msg.data is not None and msg.type is not None
        mtype = msg.type
        group_name = msg.data.get("group", "default")
        user_name = msg.data.get("username", "root")
        password = msg.data.get("password", "default")
        # Message is a chat message, send it to the associated group
        if mtype == UDPMessage.MessageType.CHT:
            text = msg.data.get("text")
            if not isinstance(text, str):
                return 400, None, "No text specified"
            time_sent = datetime.now()
            if "time_sent" in msg.data:
                time_sent = datetime.fromisoformat(msg.data["time_sent"])
            try:
                self.db_controller.new_message(group_name, user_name, text, time_sent)
            except Exception as e:
                return 500, None, f"Unable to save message: {e}"
            # Save a reference to the sequence number of the message
            msg.data["msg_seqn"] = msg.header.SEQN
            self.group_layer.group_send(group_name, msg)
            return 200, None, None
        # Message is a group add, try create a new group
        elif mtype == UDPMessage.MessageType.GRP_ADD:
            try:
                members = msg.data.get("members", [])
                self.group_layer.group_add(group_name, user_name, members)
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
        elif mtype == UDPMessage.MessageType.USR_LST:
            user_list = list(self.db_controller.user_list())
            return 200, user_list, None
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

    def on_timed_out(self, addr: Optional[Address]) -> None:
        """De-register an address if a request to a 'client' times out."""
        if addr is not None:
            self.db_controller.deregister_address(addr)


def get_host_and_port(random_port=False) -> Address:
    """Get the host and port from system args."""
    if len(sys.argv) == 3:
        host, port = sys.argv[1], int(sys.argv[2])
    elif len(sys.argv) == 2:
        host, port = sys.argv[1], 5000
    else:
        host, port = '127.0.0.1', 5000
    return (host, None) if random_port else (host, port)  # type: ignore

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
        logging.info("Caught keyboard interrupt, exiting...")
        sys.exit(0)