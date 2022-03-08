import asyncio
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Dict, Any

from PyQt5.QtWidgets import QScrollArea, QLabel, QVBoxLayout, QPushButton, QApplication
from PyQt5.QtWidgets import QSizePolicy, QLineEdit, QWidget, QHBoxLayout, QFrame
from PyQt5.QtCore import pyqtSignal, Qt, pyqtSlot
from PyQt5.QtGui import QIcon, QPixmap

from async_udp_server import UDPMessage
from .utils import LineWidget

if TYPE_CHECKING:
    from .main_window import MainWindow
else:
    MainWindow = Any


class ChatCanvas(QFrame):
    """The chat canvas displays chat messages for a particular group."""

    sendMessage = pyqtSignal(dict)
    blurbChanged = pyqtSignal(str)

    INPUT_STYLESHEET = """
        background-color: #444444;
        border-radius: 5px;
        padding: 10px;
    """
    HEADER_SS = """
        background-color: #0b2e6e;
        padding: 10px 15px;
    """
    TITLE_SS = """
        font-weight: bold;
        font-size: 20px;
    """

    class MessageWidget(QFrame):
        """A message widget displayed in the chat window."""

        MESSAGE_SS = """
            #message {
                background-color: #dddddd;
                border-radius: 8px;
                border-top-left-radius: 2px;
            }
        """
        UNAME_SS = "font-size: 14px; font-weight: bold; color: #222222"
        FOOTER_SS = "color: #444444; font-size: 13px"
        TEXT_SS = "color: black; font-size: 14px"
        DATE_SEPARATOR_SS = """
            #date_separator {
                border-radius: 5px;
                background-color: #444444;
                padding: 4px;
            }
        """

        def __init__(self, seq_id: int, text: str, username: str, time_sent: datetime):
            """Initialize a message from message data."""
            self.seq_id = seq_id
            self.text = text
            self.username = username
            self.time_sent = time_sent
            self.blurb = "No messages yet"
            self.CHECK_SINGLE = QPixmap(":/check.png").scaledToHeight(12, Qt.SmoothTransformation)
            self.CHECK_DOUBLE = QPixmap(":/check-all.png").scaledToHeight(12, Qt.SmoothTransformation)
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
            self.time_label = QLabel(self.time_sent.strftime("%I:%M %p"))
            self.ack_label = QLabel()
            self.ack_label.setPixmap(self.CHECK_SINGLE)
            footer = QWidget()
            footer.setStyleSheet(self.FOOTER_SS)
            footer_layout = QHBoxLayout(footer)
            footer_layout.setContentsMargins(0, 0, 0, 0)
            footer_layout.addStretch()
            footer_layout.addWidget(self.time_label)
            footer_layout.addWidget(self.ack_label)
            layout = QVBoxLayout(self)
            layout.addWidget(self.username_label)
            layout.addWidget(self.text_label)
            layout.addWidget(footer)

        def setPreviousMessage(self, pmsg: 'ChatCanvas.MessageWidget', layout: QVBoxLayout, index: int) -> None:
            """Set the previous message."""
            if self.time_sent.strftime('%Y-%m-%d') != pmsg.time_sent.strftime('%Y-%m-%d'):
                date_separator = QWidget()
                date_sep_layout = QHBoxLayout(date_separator)
                date_sep_layout.addWidget(LineWidget())
                date_sep_text = QLabel(self.time_sent.strftime('%d/%m/%Y'))
                date_sep_layout.addWidget(date_sep_text)
                date_sep_layout.addWidget(LineWidget())
                date_sep_text.setObjectName("date_separator")
                date_sep_text.setStyleSheet(self.DATE_SEPARATOR_SS)
                layout.insertWidget(index, date_separator)
            elif pmsg.username == self.username:
                self.username_label.setParent(None)

        def acknowledge(self):
            """Acknowledge (=double-tick) a message."""
            self.ack_label.setPixmap(self.CHECK_DOUBLE)

        def setAlignmentAccordingToUsername(self, username: str) -> None:
            """ALign the message to left or right, depending on its username."""
            al = Qt.AlignRight if username == self.username else Qt.AlignLeft
            self.parentWidget().layout().setAlignment(self, al)

    
    def __init__(self, group_name: str, mwindow: MainWindow):
        """Initialize for a given group."""
        super().__init__()
        self.group_name = group_name
        self.mwindow = mwindow
        
        self.unacknowledged_messages: Dict[int, ChatCanvas.MessageWidget] = {}

        self.group_header = QFrame()
        header_layout = QVBoxLayout(self.group_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.group_title = QLabel(group_name)
        self.group_title.setStyleSheet(self.TITLE_SS)
        header_layout.addWidget(self.group_title)
        self.group_header.setStyleSheet(self.HEADER_SS)

        self.text_input = QLineEdit()
        self.text_input.returnPressed.connect(self.onReturnPressed)
        self.text_input.setStyleSheet(self.INPUT_STYLESHEET)
        self.text_input.setPlaceholderText("Type a message")
        self.text_submit = QPushButton("Send")
        self.text_submit.setIcon(QIcon(":/send.png"))
        self.text_submit.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.text_submit.setStyleSheet("border-radius: 5px; padding: 5px 15px; background-color: #444444;")
        self.text_submit.clicked.connect(self.onReturnPressed)
        self.input_cont = QWidget()
        input_layout = QHBoxLayout(self.input_cont)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(self.text_input)
        input_layout.addWidget(self.text_submit)

        self.setLayout(QVBoxLayout())
        self.scroll_widget = QScrollArea()
        self.scroll_widget.setFrameStyle(QFrame.NoFrame)
        self.viewport_widget = QWidget()
        self.setObjectName("canvas") 
        # Ensure the background image is applied only to the background
        self.setStyleSheet("#canvas{border-image: url(':/background.jpeg') 0 0 0 0 stretch stretch;}")
        self.view_layout = QVBoxLayout(self.viewport_widget)
        # Ensure the background is visible through the viewport
        self.viewport_widget.setStyleSheet("background-color: rgba(0,0,0,0)")
        self.scroll_widget.setStyleSheet("background-color: rgba(0,0,0,0)")
        self.view_layout.addStretch()
        self.scroll_widget.setWidgetResizable(True)
        self.scroll_widget.setWidget(self.viewport_widget)
        self.layout().addWidget(self.group_header)
        self.layout().addWidget(self.scroll_widget, stretch=2)
        self.layout().addWidget(self.input_cont)
        self.scroll_widget.verticalScrollBar().rangeChanged.connect(self.onScrollChange)

    @pyqtSlot(int, int)
    def onScrollChange(self, min:int, max: int) -> None:
        """Scroll to the bottom when scrollbar size changes."""
        self.sender().setSliderPosition(max)
        
    def addMessage(self, 
                   seq_id: int,
                   text: str,
                   username: str,
                   date_sent: datetime,
                   ack: bool = False
                   ) -> MessageWidget:
        """Add a message to the canvas."""
        if seq_id in self.unacknowledged_messages:
            unack_msg = self.unacknowledged_messages[seq_id]
            unack_msg.acknowledge()
            return unack_msg
        widget = self.MessageWidget(seq_id, text, username, date_sent)
        insert_index = self.view_layout.count()
        self.view_layout.insertWidget(insert_index, widget)
        prev_msg = self.view_layout.itemAt(insert_index-1).widget()
        if prev_msg:
            widget.setPreviousMessage(prev_msg, self.view_layout, insert_index)
        if ack:
            widget.acknowledge()
        widget.setAlignmentAccordingToUsername(self.mwindow.username)
        # Change the vlurb and notify listeners
        self.blurb = text
        self.blurbChanged.emit(self.blurb)
        return widget

    def onReturnPressed(self) -> None:
        """Enter pressed, send the current message."""
        txt = self.text_input.text()
        now = datetime.now()
        uname = self.mwindow.username
        seq_id = self.mwindow.client.bytes_sent
        # Add a message to the canvas - it will be verified once the server replies
        msg = self.addMessage(seq_id, txt, uname, now)
        self.unacknowledged_messages[seq_id] = msg
        self.sendMessage.emit({
            "type": "CHT",
            "text": txt,
            "group": self.group_name,
            "time_sent": now.isoformat(),
            "username": uname
        })
        self.text_input.clear()

    def retrieveHistoricalMessages(self):
        """Retrieve historical messages from the server."""
        # Fetch the persisted messages
        self.mwindow.client.send_message({
            "type": UDPMessage.MessageType.MSG_HST.value,
            "group": self.group_name,
            "username": self.mwindow.username,
        }, on_response=self.onReceiveHistoricalMessages)

    def onReceiveHistoricalMessages(self, resp: asyncio.Future):
        """Request historical messages from the server's database."""
        if resp.exception():
            logging.error("Error retrieving historical messages.")
        else:
            msg: UDPMessage = resp.result()
            for hmsg in msg.data.get("response", []):
                timesent = datetime.fromisoformat(hmsg["Date_Sent"])
                self.addMessage(
                    None, hmsg["Text"], hmsg["Username"], timesent, ack=True)

