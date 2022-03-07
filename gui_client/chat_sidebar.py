import asyncio
from typing import TYPE_CHECKING, Any, Optional

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QDockWidget, QVBoxLayout, QWidget, QLabel, QLineEdit
from PyQt5.QtWidgets import QPushButton, QSizePolicy, QFrame, QHBoxLayout
from PyQt5.QtGui import QIcon

from async_udp_server import UDPMessage

from .chat_canvas import ChatCanvas

if TYPE_CHECKING:
    from .main_window import MainWindow
else:
    MainWindow = Any


class ChatSidebar(QDockWidget):
    """Displays chats in the sidebar."""

    HEADER_SS = """
        background-color: #0b2e6e;
    """
    TITLE_SS = """
        font-weight: bold;
        font-size: 20px;
    """
    GROUP_ADD_SS = """
        border-radius: 20px;
        background-color: #6d1596
    """

    def __init__(self, username, mwindow: 'MainWindow'):
        """Initialize the chat sidebar."""
        super().__init__()
        self.username = username
        self.active_tab: Optional[QFrame] = None

        self.content_widget = QWidget()
        self.content_widget.setLayout(QVBoxLayout())
        self.content_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.content_widget.layout().setSpacing(0)
        self.mwindow = mwindow
        # Create the groups header
        self.group_header = QFrame()
        self.group_header.setMinimumWidth(300)
        header_layout = QHBoxLayout(self.group_header)
        self.group_title = QLabel(username)
        self.group_title.setStyleSheet(self.TITLE_SS)
        self.group_add = QPushButton()
        self.group_add.setFixedSize(40,40)
        self.group_add.setIconSize(QSize(30, 30))
        self.group_add.setIcon(QIcon(":/add-group.png"))
        self.group_add.setStyleSheet(self.GROUP_ADD_SS)
        self.group_add.clicked.connect(self.onClickNewGroup)
        header_layout.addWidget(self.group_title)
        header_layout.addStretch()
        header_layout.addWidget(self.group_add)
        self.group_header.setStyleSheet(self.HEADER_SS)
        # Create new group widget
        self.new_group_widget = QFrame()
        new_group_layout = QVBoxLayout(self.new_group_widget)
        self.new_group_input = QLineEdit()
        self.new_group_input.setPlaceholderText("New group name")
        self.new_group_input.returnPressed.connect(self.onReturnGroupName)
        self.new_group_input.hide()
        self.group_warning_label = QLabel()
        self.group_warning_label.setStyleSheet("color: red")
        self.group_warning_label.hide()
        new_group_layout.addWidget(self.new_group_input)
        new_group_layout.addWidget(self.group_warning_label)
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
        self.content_widget.layout().addWidget(self.group_header)
        self.content_widget.layout().addWidget(self.new_group_widget)
        self.content_widget.layout().addWidget(self.reconnect_widget)
        self.content_widget.layout().addStretch()
        self.setWidget(self.content_widget)

    def setUsername(self, username: str) -> None:
        """Set the displayed username."""
        self.username = username
        self.group_title.setText(username)

    def onClickReconnect(self):
        """Try to reconnect when the user requests it."""
        # Try to re-start the connection
        self.mwindow.reconnect()

    def onClickNewGroup(self):
        """Run when the user clicks the new group button."""
        if not self.new_group_input.isVisible():
            self.new_group_input.show()
            self.new_group_input.setFocus()

    def onReturnGroupName(self):
        """User submitted the new group name."""
        self.group_warning_label.hide()
        group_name = self.new_group_input.text()
        self.mwindow.client.send_message({
            "type": UDPMessage.MessageType.GRP_ADD.value,
            "group": group_name,
            "username": self.username
        }, on_response=self.onCreateGroupResponse)
        self.new_group_input.clear()

    def onCreateGroupResponse(self, fut: asyncio.Future):
        """Server returned a response, created a new group."""
        if fut.exception():
            self.group_warning_label.show()
            self.group_warning_label.setText("Unable to create group")
        else:
            msg = fut.result()
            if msg.data.get("error"):
                self.group_warning_label.show()
                self.group_warning_label.setText(msg.data.get("error"))
            elif msg.data.get("status") == 200:
                self.onCreateGroup(msg.data["response"]["group"])

    def onCreateGroup(self, group_name: str) -> None:
        """Run when a group is created."""
        # Add a chat window to the main window
        new_chat_window = ChatCanvas(group_name, self.mwindow)
        self.mwindow.content_widget.addWidget(new_chat_window)
        tab = self.addChatWindow(new_chat_window)
        self.setActiveTab(tab, new_chat_window)

    def addChatWindow(self, chat_window: ChatCanvas) -> QFrame:
        """Register a chat window in the sidebar."""
        # Create the chat tab
        chat_tab = QFrame()
        chat_layout = QHBoxLayout(chat_tab)
        title_widget = QWidget()
        title_layout = QVBoxLayout(title_widget)
        title_label = QLabel(chat_window.group_name)
        title_label.setStyleSheet("font-size: 14p; font-weight: bold;")
        text_label = QLabel("No messages yet")
        title_layout.addWidget(title_label)
        title_layout.addWidget(text_label)
        chat_layout.addWidget(title_widget)
        chat_tab.mousePressEvent = lambda e: self.setActiveTab(chat_tab, chat_window)
        # Update the tab when the messages' blurb changes
        chat_window.blurbChanged.connect(lambda b: text_label.setText(b))
        # Allow the window to send messages
        chat_window.sendMessage.connect(self.mwindow.sendMessage)
        idx = self.widget().layout().count() - 1
        self.widget().layout().insertWidget(idx, chat_tab)
        return chat_tab

    def setActiveTab(self, chat_tab: QFrame, chat_window: ChatCanvas):
        """Set the active chat tab."""
        if self.active_tab:
            self.active_tab.setStyleSheet(None)
        self.active_tab = chat_tab
        self.active_tab.setStyleSheet("background-color: grey;")
        self.mwindow.content_widget.setCurrentWidget(chat_window)


