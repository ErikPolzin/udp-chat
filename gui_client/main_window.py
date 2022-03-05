import asyncio
from typing import List, Optional
from datetime import datetime
from queue import Queue
import logging

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

        self.content_widget = QStackedWidget()
        self.content_widget.setContentsMargins(0, 0, 0, 0)
        self.sidebar_widget = ChatSidebar("root", self)
        initial_window = ChatCanvas("default", self)
        # Start off with just the 'default' group
        self.setCentralWidget(self.content_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_widget)
        self.setWindowTitle("UDP Chat Client")
        self.client: Optional[ClientChatProtocol] = None
        self.content_widget.addWidget(initial_window)
        tab = self.sidebar_widget.addChatWindow(initial_window)
        self.sidebar_widget.setActiveTab(tab, initial_window)

    def onReceiveMessage(self, msg: UDPMessage):
        """Client received a new message."""
        if msg.type == UDPMessage.MessageType.CHT:
            try:
                text = msg.data["text"]
                username = msg.data["username"]
                time_sent = datetime.fromisoformat(msg.data["time_sent"])
            except KeyError as k:
                logging.warning(f"Received improperly formatted message (missing '{k}'")
                return
            w = self.getChatWindow(msg.data.get("group"))
            if w:
                w.addMessage(msg.header.SEQN, text, username, time_sent, ack=True)

    async def create_client(self, server_addr: Address):
        """Await the creation of a new client."""
        self.client: ClientChatProtocol = await ClientChatProtocol.create(server_addr)
        self.client.on_con_lost.add_done_callback(self.onLostConnection)
        self.client.add_server_connected_listener(self.onCreatedConnection)
        logging.info(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
        # Allow the GUI to receive messages from the client
        self.client.set_receive_listener(self.onReceiveMessage)
        # Only fetch messages if this is the first time connecting to the server
        if self.first_connect:
            self.fetchGroups()
            self.first_connect = False

    def reconnect(self):
        """Re-establish the connection to the server."""
        asyncio.create_task(self.create_client(self.server_addr))

    def sendMessage(self, data):
        """A chat window has requested to send a message."""
        self.client.send_message(data, on_response=self.onSendMessage)

    def chatWindows(self) -> List[ChatCanvas]:
        """List all the chat windows."""
        windows = []
        for i in range(self.content_widget.count()):
            windows.append(self.content_widget.widget(i))
        return windows

    def getChatWindow(self, group_name: str) -> Optional[ChatCanvas]:
        """Get the chat window for a specific group."""
        for window in self.chatWindows():
            if window.group_name == group_name:
                return window

    def onLostConnection(self, on_con_lost: asyncio.Future) -> None:
        """Show the reconnect widget when the connection to the server is lost."""
        self.sidebar_widget.reconnect_widget.show()
        for w in self.chatWindows():
            w.input_cont.setDisabled(True)

    def onCreatedConnection(self) -> None:
        """Hide the reconnect widget when the connection to the server is lost."""
        self.sidebar_widget.reconnect_widget.hide()
        # Enable the input widget/send button when connected to the server
        for w in self.chatWindows():
            w.input_cont.setDisabled(False)
        # Try to clear the message backlog
        logging.debug(f"{self.message_backlog.qsize()} message(s) in backlog.")
        while not self.message_backlog.empty():
            self.client.send_message(msg=self.message_backlog.get(), on_response=self.onSendMessage)

    def onSendMessage(self, response: asyncio.Future):
        """Add a message to the backlog if sending it fails."""
        if isinstance(response.exception(), RequestTimedOutException):
            msg: UDPMessage = response.request
            # Add the message to the backlog - it will be sent again once reconnected
            if msg.type == UDPMessage.MessageType.CHT:
                logging.debug("Added message to backlog")
                self.message_backlog.put(msg)

    def fetchGroups(self):
        """Fetch all groups that this user is part of."""
        # Fetch the persisted messages
        self.client.send_message({
            "type": UDPMessage.MessageType.GRP_HST.value,
            "group": "default",
            "username": "root",
        }, on_response=self.onFetchedGroups)

    def onFetchedGroups(self, resp: asyncio.Future):
        """Request historical messages from the server's database."""
        if resp.exception():
            wlab = self.sidebar_widget.group_warning_label
            wlab.show()
            wlab.setText("Error retrieving groups.")
        else:
            msg: UDPMessage = resp.result()
            for g in msg.data.get("response", []):
                window = ChatCanvas(g["Name"], self)
                self.content_widget.addWidget(window)
                self.sidebar_widget.addChatWindow(window)
            for w in self.chatWindows():
                w.retrieveHistoricalMessages()
