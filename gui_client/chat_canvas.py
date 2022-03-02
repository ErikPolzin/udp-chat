from PyQt5.QtWidgets import QScrollArea, QLabel, QVBoxLayout, QSizePolicy, QLineEdit
from PyQt5.QtCore import pyqtSignal


class ChatCanvas(QScrollArea):
    """The chat canvas displays chat messages for a particular group."""

    sendMessage = pyqtSignal(dict)
    INPUT_STYLESHEET = """
        background-color: #444444;
        border-radius: 5px;
        margin-top: 10px;
        padding: 10px;
    """
    MESSAGE_STYLESHEET = """
        background-color: #dddddd;
        padding: 10px;
        border-radius: 10px;
        color: black
    """

    
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
        
    def addMessage(self, text):
        """Add a message to the canvas."""
        widget = QLabel(text)
        widget.setStyleSheet(self.MESSAGE_STYLESHEET)
        widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.layout().insertWidget(self.layout().count()-1, widget)

    def onReturnPressed(self):
        """Enter pressed, send the current message."""
        msgdata = {"type": "CHT", "text": self.text_input.text(), "group": self.group_name}
        self.sendMessage.emit(msgdata)
        self.text_input.clear()

