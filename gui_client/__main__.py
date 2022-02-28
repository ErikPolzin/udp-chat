import asyncio
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QDockWidget

from async_udp_client import ClientChatProtocol
from async_udp_server import Address, ChatMessage, get_host_and_port


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
        self.setCentralWidget(self.content_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_widget)
        self.setWindowTitle("UDP Chat Client")
        self.is_exited = False
        self.client: Optional[ClientChatProtocol] = None

    def onReceiveMessage(self, msg: ChatMessage):
        """Client received a new message."""
        print("GUI: received message", msg)

    async def create_client(self, server_addr: Address):
        """Await the creation of a new client."""
        self.client: ClientChatProtocol = await ClientChatProtocol.create(server_addr)
        self.client.set_receive_listener(self.onReceiveMessage)

    async def mainLoop(self, server_addr: Address):
        """Run the Qt event loop and asyncio event loop side-by-side."""
        print(f"Listening for events from {server_addr[0]}:{server_addr[1]}...")
        # No authentication, so we can do this immediately. Eventually we'll have
        # to delay creating the client until the user has logged in.
        await self.create_client(server_addr)
        app = QApplication.instance()
        while not self.is_exited:
            app.processEvents()
            await asyncio.sleep(0)
        print("Application exited")

    def closeEvent(self, a0: QCloseEvent) -> None:
        """Update the is_exited boolean."""
        self.is_exited = True
        return super().closeEvent(a0)


if __name__ == "__main__":
    server_addr = get_host_and_port()
    app = QApplication([])

    window = MainWindow()
    window.show()

    loop = asyncio.get_event_loop()
    # Create a separate task to run PyQt and asyncio alongside oneanother
    window_loop_task = asyncio.ensure_future(window.mainLoop(server_addr))
    loop.run_until_complete(window_loop_task)
