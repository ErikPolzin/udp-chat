from PyQt5.QtWidgets import QScrollArea, QLabel, QVBoxLayout
from PyQt5.QtWidgets import QSizePolicy, QLineEdit, QWidget, QHBoxLayout, QFrame
from PyQt5.QtCore import pyqtSignal
from datetime import datetime


class ChatCanvas(QScrollArea):
    """The chat canvas displays chat messages for a particular group."""

    sendMessage = pyqtSignal(dict)
    INPUT_STYLESHEET = """
        background-color: #444444;
        border-radius: 5px;
        margin-top: 10px;
        padding: 10px;
    """

    class MessageWidget(QFrame):
        """A message widget displayed in the chat window."""

        MESSAGE_SS = """
            #message {
                background-color: #dddddd;
                padding: 10px;
                border-radius: 8px;
            }
        """
        UNAME_SS = "font-size: 14px; font-weight: bold; color: #222222"
        FOOTER_SS = "margin: 0; color: light-grey; font-size: 10px"
        TEXT_SS = "color: black; font-size: 12px"

        def __init__(self, text: str, username: str, time_sent: datetime):
            """Initialize a message from message data."""
            self.text = text
            self.username = username
            self.time_sent = time_sent
            super().__init__()
            self.setAutoFillBackground(True)
            self.setObjectName("message")
            self.setStyleSheet(self.MESSAGE_SS)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
            self.initUI()
            
        def initUI(self):
            """Initialize message UI."""
            self.username_label = QLabel(self.username)
            self.username_label.setStyleSheet(self.UNAME_SS)
            self.text_label = QLabel(self.text)
            self.text_label.setStyleSheet(self.TEXT_SS)
            self.time_label = QLabel(self.time_sent.strftime("%-I:%S %p"))
            footer = QWidget()
            footer.setStyleSheet(self.FOOTER_SS)
            footer_layout = QHBoxLayout(footer)
            footer_layout.setContentsMargins(4, 0, 4, 0)
            footer_layout.setSpacing(0)
            footer_layout.addStretch()
            footer_layout.addWidget(self.time_label)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.username_label)
            layout.addWidget(self.text_label)
            layout.addWidget(footer)

        def setPreviousMessage(self, pmsg: 'ChatCanvas.MessageWidget') -> None:
            """Set the previous message."""
            if pmsg.username == self.username:
                self.username_label.setParent(None)

    
    def __init__(self, group_name: str):
        """Initialize for a given group."""
        super().__init__()
        self.group_name = group_name
        self.text_input = QLineEdit()
        self.text_input.returnPressed.connect(self.onReturnPressed)
        self.text_input.setStyleSheet(self.INPUT_STYLESHEET)
        # Ensure the background image is applied only to the background
        self.setObjectName("canvas") 
        self.setStyleSheet("#canvas{border-image: url(':/background.jpeg') 0 0 0 0 stretch stretch;}")
        self.setLayout(QVBoxLayout())
        self.layout().addStretch()
        self.layout().addWidget(self.text_input)
        
    def addMessage(self, text: str, username: str, time_sent: datetime) -> None:
        """Add a message to the canvas."""
        widget = self.MessageWidget(text, username, time_sent)
        insert_index = self.layout().count()-1
        self.layout().insertWidget(insert_index, widget)
        prev_msg = self.layout().itemAt(insert_index-1).widget()
        if prev_msg:
            widget.setPreviousMessage(prev_msg)

    def onReturnPressed(self):
        """Enter pressed, send the current message."""
        msgdata = {
            "type": "CHT",
            "text": self.text_input.text(),
            "group": self.group_name,
            "time_sent": datetime.now().isoformat(),
            "username": "root"
        }
        self.sendMessage.emit(msgdata)
        self.text_input.clear()

