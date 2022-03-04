from typing import TYPE_CHECKING, Any

from PyQt5.QtWidgets import QDockWidget, QVBoxLayout, QWidget, QLabel, QPushButton, QSizePolicy
if TYPE_CHECKING:
    from .main_window import MainWindow
else:
    MainWindow = Any


class ChatSidebar(QDockWidget):
    """Displays chats in the sidebar."""

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
        self.mwindow.reconnect()