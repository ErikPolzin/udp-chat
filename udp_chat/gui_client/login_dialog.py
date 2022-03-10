import asyncio
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QWidget, QHBoxLayout, QGridLayout

from udp_chat.protocol import UDPMessage
from .utils import CircularSpinner

if TYPE_CHECKING:
    from .main_window import MainWindow


class LoginDialog(QDialog):
    """The login dialog allows the user to create or sign in to an account."""

    TEXT_SS = "font-size: 14px;"

    BUTTON_SS = """
        background-color: #4a4a4a;
        border-style: outset;
        border-width: 1px;
        border-radius: 2px;
        padding: 4px;
        border-color: #000000;
    """
    DIALOG_SS = "background-color: #2e2e2e;"

    INPUT_SS = """
        background-color: #545454;
        border-style: outset;
        border-radius: 2px;
        padding: 3px;
        border-color: #5e5e5e;
        border-width: 1px;
    """

    MIN_PASSWORD_LENGTH = 6

    def __init__(self, mwindow: 'MainWindow'):
        super().__init__()
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.mwindow = mwindow
        self.setWindowTitle("UDP Chat Login")
        self.resize(500, 120)

        mwindow.connectingToServer.connect(
            lambda: self.showFeedback("Connecting to server...", loading=True))
        mwindow.connectionTimedOut.connect(
            lambda: self.showError("Unable to reach server"))
        mwindow.connectedToServer.connect(
            lambda: self.showSuccess("Connected to server!"))

        layout = QVBoxLayout()

        usernameLabel = QLabel("Username")
        usernameLabel.setStyleSheet(self.TEXT_SS)
        self.username = QLineEdit()
        self.username.setStyleSheet(self.INPUT_SS)
        usernameLayout = QGridLayout()
        usernameWidget = QWidget()
        usernameLayout.addWidget(usernameLabel, 0, 0)
        usernameLayout.addWidget(self.username, 0, 1)
        usernameLayout.setColumnMinimumWidth(0, 70)
        usernameWidget.setLayout(usernameLayout)
        layout.addWidget(usernameWidget)

        passwordLabel = QLabel("Password")
        passwordLabel.setStyleSheet(self.TEXT_SS)
        self.password = QLineEdit()
        # Hide the password field input
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setInputMethodHints(
            Qt.ImhHiddenText| Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase)
        self.password.setStyleSheet(self.INPUT_SS)
        passwordLayout = QGridLayout()
        passwordWidget = QWidget()
        passwordLayout.addWidget(passwordLabel, 0, 0)
        passwordLayout.addWidget(self.password, 0, 1)
        passwordLayout.setColumnMinimumWidth(0, 70)
        passwordWidget.setLayout(passwordLayout)
        layout.addWidget(passwordWidget)

        login_button = QPushButton("Login")
        login_button.setStyleSheet(self.BUTTON_SS)
        login_button.clicked.connect(
            lambda: self.verify_credentials(
                self.username.text(), self.password.text()))
        layout.addWidget(login_button, 3)

        create_account_button = QPushButton("Create Account")
        create_account_button.setStyleSheet(self.BUTTON_SS)
        create_account_button.clicked.connect(
            lambda: self.create_account(
                self.username.text(), self.password.text()))
        layout.addWidget(create_account_button)

        # Construct the feedback widget
        self.feedbackWidget = QWidget()
        feedbackLayout = QHBoxLayout(self.feedbackWidget)
        self.feedbackLoader = CircularSpinner(self.feedbackWidget)
        self.feedbackLabel = QLabel("Feedback placeholder")
        feedbackLayout.addWidget(self.feedbackLoader)
        feedbackLayout.addWidget(self.feedbackLabel)
        layout.addWidget(self.feedbackWidget)
        self.feedbackWidget.hide()

        self.setLayout(layout)
        self.setStyleSheet(self.DIALOG_SS)

    def create_account(self, username: str, password: str):
        """Request the server to create a new account."""
        if len(password) < self.MIN_PASSWORD_LENGTH:
            self.showError("Password is too short!")
            return
        self.showFeedback("Creating account...", loading=True)
        self.mwindow.client.send_message({
            "type": UDPMessage.MessageType.USR_ADD.value,
            "username": username,
            "password": password,
        }, on_response=self.on_account_creation)

    def on_account_creation(self, resp: asyncio.Future):
        """Server created an accound, or returned an error."""
        if resp.exception():
            self.showError("Could not reach server..")
            return
        msg: UDPMessage = resp.result()
        if msg.data is None:
            return
        g = msg.data.get("response", {})
        created = g.get("created_user", False)
        if not created:
            self.showError("Username already in use.")
        else:
            self.showSuccess("Account creation successful.")

    def verify_credentials(self, username: str, password: str):
        """Send account verification to the server."""
        self.showFeedback("Loggin in...", loading=True)
        self.mwindow.client.send_message({
            "type": UDPMessage.MessageType.USR_LOGIN.value,
            "username": username,
            "password": password,
        }, on_response=self.on_login)

    def on_login(self, resp: asyncio.Future):
        """Server returned a login reponse."""
        if resp.exception():
            self.showError("Could not contact server.")
            return
        msg: UDPMessage = resp.result()
        if msg.data is None:
            return
        response_code = msg.data.get("status")
        response_data = msg.data.get("response", {})
        if response_code != 200:
            self.showError(f"Login unsuccessful: {msg.data.get('error')}")
        else:
            self.done(1)
            username = response_data.get("username")
            if username is not None:
                self.mwindow.onLogin(username)

    def clearFeedback(self):
        """Hide the user feedback label."""
        self.feedbackWidget.hide()

    def showFeedback(self, text: str, fg: str = "none", bg: str = "none", loading: bool = False):
        """Show feedback text with a given style and optional circular loader."""
        self.feedbackLabel.setText(text)
        self.feedbackWidget.setStyleSheet(f"background-color: {bg}; color: {fg}; font-weight: bold;")
        self.feedbackWidget.show()
        if loading:
            self.feedbackLoader.show()
        else:
            self.feedbackLoader.hide()

    def showError(self, text: str) -> None:
        """Show an error message."""
        self.showFeedback(text, fg="white", bg="#911d1d")

    def showSuccess(self, text: str) -> None:
        """Show a success message."""
        self.showFeedback(text, fg="white", bg="green")