import asyncio
from typing import List, Optional
from datetime import datetime
from queue import Queue
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QStackedWidget, QGridLayout, QLabel, QLineEdit, QPushButton, QDialog, QVBoxLayout

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
        self.username = None

        self.content_widget = QStackedWidget()
        self.content_widget.setContentsMargins(0, 0, 0, 0)
        self.sidebar_widget = ChatSidebar("Not logged in", self)
        initial_window = ChatCanvas("default", self)
        # Start off with just the 'default' group
        self.setCentralWidget(self.content_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_widget)
        self.setWindowTitle("UDP Chat Client")
        self.client: Optional[ClientChatProtocol] = None
        self.content_widget.addWidget(initial_window)
        tab = self.sidebar_widget.addChatWindow(initial_window)
        self.sidebar_widget.setActiveTab(tab, initial_window)
        self.login_dialog = LoginDialog(self)

    def execute_login(self):
        """Show the login dialog."""
        self.login_dialog.show()

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
        self.execute_login()

    def reconnect(self):
        """Re-establish the connection to the server."""
        asyncio.create_task(self.create_client(self.server_addr))

    def sendMessage(self, data):
        """A chat window has requested to send a message."""
        self.client.send_message(data, on_response=self.onSendMessage)

    def verify_credentials(self, username: str, password: str):
        """Send account verification to the server."""
        self.client.send_message({
            "type": UDPMessage.MessageType.USR_LOGIN.value,
            "username": username,
            "password": password,
        }, on_response=self.on_login)

    def on_login(self, resp: asyncio.Future):
        """Server returned a login reponse."""
        wlab = self.login_dialog.login_warning_label
        if resp.exception():
            wlab.show()
            wlab.setText("Error logging in.")
            return
        msg: UDPMessage = resp.result()
        response_code = msg.data.get("status")
        response_data = msg.data.get("response", {})
        if response_code != 200:
            wlab.show()
            wlab.setText(f"Login unsuccessful: {msg.data.get('error')}")
        else:
            if not response_data.get("credentials_valid"):
                wlab.show()
                wlab.setText("Credentials invalid")
                return
            self.login_dialog.done(1)
            self.username = msg.data.get("response", {}).get("username")
            self.fetchGroups()
            self.sidebar_widget.setUsername(self.username)

    def create_account(self, username: str, password: str):
        self.client.send_message({
            "type": UDPMessage.MessageType.USR_ADD.value,
            "username": username,
            "password": password,
        }, on_response=self.on_account_creation)

    def on_account_creation(self, resp: asyncio.Future):
        wlab = self.login_dialog.login_warning_label
        if resp.exception():
            wlab.show()
            wlab.setText("Could not reach server..")
            return
        msg: UDPMessage = resp.result()
        g = msg.data.get("response", {})
        created = g.get("created_user", False)
        wlab.show()
        if not created:
            wlab.setText("Username already in use.")
        else:
            wlab.setText("Account creation successful.")        

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

    def fetchGroups(self) -> None:
        self.client.send_message({
            "type": UDPMessage.MessageType.GRP_HST.value,
            "username": self.username,
        }, on_response=self.onFetchedGroups)

    def onFetchedGroups(self, resp3: asyncio.Future):
        """Request historical messages from the server's database."""
        if resp3.exception():
            wlab = self.sidebar_widget.group_warning_label
            wlab.show()
            wlab.setText("Error retrieving groups.")
        else:
            msg: UDPMessage = resp3.result()
            for g in msg.data.get("response", []):
                window = ChatCanvas(g["Name"], self)
                self.content_widget.addWidget(window)
                self.sidebar_widget.addChatWindow(window)
            for w in self.chatWindows():
                w.retrieveHistoricalMessages()

class LoginDialog(QDialog):

    TEXT_SS = "color: black; font-size: 14px;"

    BUTTON_SS = """
        background-color: #262625;
        color: #f5b049;`
    """


    def __init__(self, mwindow: 'MainWindow'):
        super().__init__()
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.mwindow = mwindow
        self.setWindowTitle("UDP Chat Login")
        self.resize(500, 120)

        layout = QVBoxLayout()

        self.username = QLabel("Username")
        self.username.setStyleSheet(self.TEXT_SS)
        self.lineEdit_username = QLineEdit()
        layout.addWidget(self.username)
        layout.addWidget(self.lineEdit_username)

        self.password = QLabel("Password")
        self.password.setStyleSheet(self.TEXT_SS)
        self.lineEdit_password = QLineEdit()
        self.lineEdit_password.setEchoMode(QLineEdit.Password)
        self.lineEdit_password.setInputMethodHints(
            Qt.ImhHiddenText| Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase)
        layout.addWidget(self.password)
        layout.addWidget(self.lineEdit_password)

        login_button = QPushButton("Login")
        login_button.setStyleSheet(self.BUTTON_SS)
        login_button.clicked.connect(
            lambda: self.mwindow.verify_credentials(
                self.lineEdit_username.text(), self.lineEdit_password.text()))
        layout.addWidget(login_button, 3)

        create_account_button = QPushButton("Create Account")
        create_account_button.setStyleSheet(self.BUTTON_SS)
        create_account_button.clicked.connect(
            lambda: self.mwindow.create_account(
                self.lineEdit_username.text(), self.lineEdit_password.text()))
        layout.addWidget(create_account_button)

        self.login_warning_label = QLabel()
        self.login_warning_label.setStyleSheet("color: red")
        self.login_warning_label.hide()
        layout.addWidget(self.login_warning_label)

        self.setLayout(layout)
