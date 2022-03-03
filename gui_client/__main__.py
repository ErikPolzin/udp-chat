import asyncio
from typing import Optional
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QSizePolicy
from PyQt5.QtWidgets import QDockWidget, QVBoxLayout, QWidget, QLabel, QPushButton

from async_udp_client import ClientChatProtocol
from async_udp_server import Address, UDPMessage, get_host_and_port
import resources

from .chat_canvas import ChatCanvas

try:
    from qasync import QEventLoop
except ImportError:
    print("The GUI needs qasync to run, please install it!")


class ChatSidebar(QDockWidget):
    """Placeholder class."""

    def __init__(self, mwindow: 'MainWindow'):
        """Initialize the chat sidebar."""
        super().__init__()
        self.content_widget = QWidget()
        self.content_widget.setLayout(QVBoxLayout())
        self.content_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.mwindow = mwindow
        # Create a reconnect widget
        self.reconnect_button = QPushButton("Reconnect")
        self.reconnect_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.reconnect_button.clicked.connect(self.onClickReconnect)
        self.reconnect_widget = QWidget()
        self.reconnect_widget.setStyleSheet("background-color: #7d1111")
        self.reconnect_widget.setLayout(QVBoxLayout())
        self.reconnect_widget.layout().addWidget(QLabel("Connection to server lost"))
        self.reconnect_widget.layout().addWidget(self.reconnect_button)
        # self.reconnect_widget.hide()
        self.content_widget.layout().addWidget(self.reconnect_widget)
        self.content_widget.layout().addStretch()
        self.setWidget(self.content_widget)

    def onClickReconnect(self):
        """Try to reconnect when the user requests it."""
        # Try to re-start the connection
        asyncio.create_task(self.mwindow.create_client(self.mwindow.server_addr))


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
        self.first_connect = True

        self.sidebar_widget = ChatSidebar(self)
        self.content_widget = QStackedWidget()
        self.canvas = ChatCanvas("default")
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
            self.canvas.addMessage(text, username, time_sent)

    async def create_client(self, server_addr: Address):
        """Await the creation of a new client."""
        self.client: ClientChatProtocol = await ClientChatProtocol.create(server_addr)
        self.client.on_con_lost.add_done_callback(self.onLostConnection)
        self.client.add_server_connected_listener(self.onCreatedConnection)
        print(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
        # Allow the GUI to receive messages from the client
        self.client.set_receive_listener(self.onReceiveMessage)
        # Allow the GUI to send messages to the client
        self.canvas.sendMessage.connect(self.client.send_message)
        # Only fetch messages if this is the first time connecting to the server
        if self.first_connect:
            # Fetch the persisted messages
            self.client.send_message({
                "type": UDPMessage.MessageType.MSG_HST.value,
                "group": "default",
                "username": "root",
            }, on_response=self.onReceiveHistoricalMessages)
            self.first_connect = False

    def onReceiveHistoricalMessages(self, resp: asyncio.Future):
        """Request historical messages from the server's database."""
        if resp.exception():
            print("Error retrieving historical messages.")
        else:
            msg: UDPMessage = resp.result()
            for hmsg in msg.data.get("response", []):
                self.canvas.addMessage(
                    hmsg["Text"],
                    hmsg["Username"],
                    datetime.fromisoformat(hmsg["Date_Sent"]))

    def onLostConnection(self, on_con_lost: asyncio.Future) -> None:
        """Show the reconnect widget when the connection to the server is lost."""
        self.sidebar_widget.reconnect_widget.show()
        self.canvas.input_cont.setDisabled(True)

    def onCreatedConnection(self) -> None:
        """Hide the reconnect widget when the connection to the server is lost."""
        # self.sidebar_widget.reconnect_widget.hide()
        # Enable the input widget/send button when connected to the server
        self.canvas.input_cont.setDisabled(False)



if __name__ == "__main__":
    server_addr = get_host_and_port()
    app = QApplication([])

    window = MainWindow(server_addr)
    window.showMaximized()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        # Create a separate task to run PyQt and asyncio alongside oneanother
        asyncio.create_task(window.create_client(server_addr))
        loop.run_forever()
        print("Application exited.")
