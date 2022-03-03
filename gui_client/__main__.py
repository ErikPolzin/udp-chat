import asyncio
from typing import Optional
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QDockWidget

from async_udp_client import ClientChatProtocol
from async_udp_server import Address, ChatMessage, get_host_and_port
import resources

from .chat_canvas import ChatCanvas

try:
    from qasync import QEventLoop
except ImportError:
    print("The GUI needs qasync to run, please install it!")


class ChatSidebar(QDockWidget):
    """Placeholder class."""
    pass


class MainWindow(QMainWindow):
    """Main application window.
    
    Contains a sidebar and a main content area.
    The content area is a QStackedWidget with multiple 'pages' available.

    The main window awaits a new ClientChatProtocol object, with which it can
    send and receive new chat messages.

    Receiving messages: see the 'onReceiveMessage' method.
    Sending messages: self.client.send_message(data | message)
    """

    def __init__(self):
        """Initialize the UI."""
        super().__init__()
        self.sidebar_widget = ChatSidebar()
        self.content_widget = QStackedWidget()
        self.canvas = ChatCanvas("default")
        self.setCentralWidget(self.content_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_widget)
        self.setWindowTitle("UDP Chat Client")
        self.client: Optional[ClientChatProtocol] = None
        self.content_widget.addWidget(self.canvas)

    def onReceiveMessage(self, msg: ChatMessage):
        """Client received a new message."""
        if msg.type == ChatMessage.MessageType.CHT:
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
        print(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
        # Allow the GUI to receive messages from the client
        self.client.set_receive_listener(self.onReceiveMessage)
        # Allow the GUI to send messages to the client
        self.canvas.sendMessage.connect(self.client.send_message)
        # Fetch the persisted messages
        self.client.send_message({
            "type": ChatMessage.MessageType.MSG_HST.value,
            "group": "default",
            "username": "root",
        }, on_response=self.onReceiveHistoricalMessages)

    def onReceiveHistoricalMessages(self, resp: asyncio.Future):
        """Request historical messages from the server's database."""
        if resp.exception():
            print("Error retrieving historical messages.")
        else:
            msg: ChatMessage = resp.result()
            for hmsg in msg.data.get("response", []):
                self.canvas.addMessage(
                    hmsg["Text"],
                    hmsg["Username"],
                    datetime.fromisoformat(hmsg["Date_Sent"]))


if __name__ == "__main__":
    server_addr = get_host_and_port()
    app = QApplication([])

    window = MainWindow()
    window.showMaximized()

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        # Create a separate task to run PyQt and asyncio alongside oneanother
        asyncio.create_task(window.create_client(server_addr))
        loop.run_forever()
        print("Application exited.")
