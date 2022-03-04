import asyncio
from typing import Optional
from datetime import datetime
from functools import partial
from queue import Queue

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QStackedWidget

from async_udp_client import ClientChatProtocol
from async_udp_server import Address, UDPMessage

from .chat_sidebar import ChatSidebar
from .chat_canvas import ChatCanvas
from exceptions import RequestTimedOutException


class MainWindow(QMainWindow):
    """Main application window.
    
    Contains a sidebar and a main content area.
    The content area is a QStackedWidget with multiple 'pages' available.

    The main window awaits a new ClientChatProtocol object, with which it can
    send and receive new chat messages.

    Receiving messages: see the 'onReceiveMessage' method.
    Sending messages: self.client.send_message(data | message)
    """

    def __init__(self, server_addr: Address):
        """Initialize the UI."""
        super().__init__()
        self.server_addr = server_addr
        self.message_backlog: Queue[UDPMessage] = Queue()
        self.first_connect = True

        self.sidebar_widget = ChatSidebar(self)
        self.content_widget = QStackedWidget()
        self.canvas = ChatCanvas("default", self)
        # Disable canvas input until connected to the server
        self.canvas.input_cont.setDisabled(True)
        self.setCentralWidget(self.content_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_widget)
        self.setWindowTitle("UDP Chat Client")
        self.client: Optional[ClientChatProtocol] = None
        self.content_widget.addWidget(self.canvas)

    def onReceiveMessage(self, msg: UDPMessage):
        """Client received a new message."""
        if msg.type == UDPMessage.MessageType.CHT:
            try:
                text = msg.data["text"]
                username = msg.data["username"]
                time_sent = datetime.fromisoformat(msg.data["time_sent"])
            except KeyError as k:
                print(f"Received improperly formatted message (missing '{k}'")
                return
            self.canvas.addMessage(msg.header.SEQN, text, username, time_sent, ack=True)

    async def create_client(self, server_addr: Address):
        """Await the creation of a new client."""
        self.client: ClientChatProtocol = await ClientChatProtocol.create(server_addr)
        self.client.on_con_lost.add_done_callback(self.onLostConnection)
        self.client.add_server_connected_listener(self.onCreatedConnection)
        print(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
        # Allow the GUI to receive messages from the client
        self.client.set_receive_listener(self.onReceiveMessage)
        # Allow the GUI to send messages to the client
        self.canvas.sendMessage.connect(
            partial(self.client.send_message, on_response=self.onSendMessage))
        # Only fetch messages if this is the first time connecting to the server
        if self.first_connect:
            # Fetch the persisted messages
            self.client.send_message({
                "type": UDPMessage.MessageType.MSG_HST.value,
                "group": "default",
                "username": "root",
            }, on_response=self.onReceiveHistoricalMessages)
            self.first_connect = False

    def reconnect(self):
        """Re-establish the connection to the server."""
        asyncio.create_task(self.create_client(self.server_addr))

    def onReceiveHistoricalMessages(self, resp: asyncio.Future):
        """Request historical messages from the server's database."""
        if resp.exception():
            print("Error retrieving historical messages.")
        else:
            msg: UDPMessage = resp.result()
            for hmsg in msg.data.get("response", []):
                self.canvas.addMessage(
                    None,
                    hmsg["Text"],
                    hmsg["Username"],
                    datetime.fromisoformat(hmsg["Date_Sent"]),
                    ack=True)

    def onLostConnection(self, on_con_lost: asyncio.Future) -> None:
        """Show the reconnect widget when the connection to the server is lost."""
        self.sidebar_widget.reconnect_widget.show()
        self.canvas.input_cont.setDisabled(True)

    def onCreatedConnection(self) -> None:
        """Hide the reconnect widget when the connection to the server is lost."""
        self.sidebar_widget.reconnect_widget.hide()
        # Enable the input widget/send button when connected to the server
        self.canvas.input_cont.setDisabled(False)
        # Try to clear the message backlog
        print(f"{self.message_backlog.qsize()} message(s) in backlog.")
        while not self.message_backlog.empty():
            self.client.send_message(msg=self.message_backlog.get(), on_response=self.onSendMessage)

    def onSendMessage(self, response: asyncio.Future):
        """Add a message to the backlog if sending it fails."""
        if isinstance(response.exception(), RequestTimedOutException):
            msg: UDPMessage = response.request
            # Add the message to the backlog - it will be sent again once reconnected
            if msg.type == UDPMessage.MessageType.CHT:
                print("Added message to backlog")
                self.message_backlog.put(msg)
