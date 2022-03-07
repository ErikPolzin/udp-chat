import asyncio
from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

from async_udp_server import UDPMessage

if TYPE_CHECKING:
    from .main_window import MainWindow


class LoginDialog(QDialog):
    """The login dialog allows the user to create or sign in to an account."""

    TEXT_SS = "font-size: 14px;"

    BUTTON_SS = """
        background-color: #262625;
        color: #f5b049;
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
        # Hide the password field input
        self.lineEdit_password.setEchoMode(QLineEdit.Password)
        self.lineEdit_password.setInputMethodHints(
            Qt.ImhHiddenText| Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase)
        layout.addWidget(self.password)
        layout.addWidget(self.lineEdit_password)

        login_button = QPushButton("Login")
        login_button.setStyleSheet(self.BUTTON_SS)
        login_button.clicked.connect(
            lambda: self.verify_credentials(
                self.lineEdit_username.text(), self.lineEdit_password.text()))
        layout.addWidget(login_button, 3)

        create_account_button = QPushButton("Create Account")
        create_account_button.setStyleSheet(self.BUTTON_SS)
        create_account_button.clicked.connect(
            lambda: self.create_account(
                self.lineEdit_username.text(), self.lineEdit_password.text()))
        layout.addWidget(create_account_button)

        self.login_warning_label = QLabel()
        self.login_warning_label.setStyleSheet("color: red")
        self.login_warning_label.hide()
        layout.addWidget(self.login_warning_label)

        self.setLayout(layout)

    def create_account(self, username: str, password: str):
        """Request the server to create a new account."""
        self.mwindow.client.send_message({
            "type": UDPMessage.MessageType.USR_ADD.value,
            "username": username,
            "password": password,
        }, on_response=self.on_account_creation)

    def on_account_creation(self, resp: asyncio.Future):
        """Server created an accound, or returned an error."""
        wlab = self.login_warning_label
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

    def verify_credentials(self, username: str, password: str):
        """Send account verification to the server."""
        self.mwindow.client.send_message({
            "type": UDPMessage.MessageType.USR_LOGIN.value,
            "username": username,
            "password": password,
        }, on_response=self.on_login)

    def on_login(self, resp: asyncio.Future):
        """Server returned a login reponse."""
        wlab = self.login_warning_label
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
            self.done(1)
            username = msg.data.get("response", {}).get("username")
            self.mwindow.onLogin(username) 