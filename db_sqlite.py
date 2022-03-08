from typing import Dict, List, Tuple
from datetime import datetime
from exceptions import ItemNotFoundException
import sqlite3
from sqlite3 import Error
import logging
import urllib.parse
import os
import hashlib
import hmac
import base64

class DatabaseController(object):

    def __init__(self, db_name: str = "udp_chat.sqlite"):
        """Create a new database controller with given parameters."""

        # Controller constants
        self.db_name = db_name

        # Create the database if it doesn't exist
        user_query = """CREATE TABLE IF NOT EXISTS User (
            UserID INTEGER PRIMARY KEY,
            Address TEXT,
            Username TEXT NOT NULL UNIQUE,
            Password TEXT NOT NULL
            );"""
        group_query = """CREATE TABLE IF NOT EXISTS Room (
            RoomID INTEGER PRIMARY KEY,
            Name TEXT NOT NULL UNIQUE,
            Password TEXT,
            Date_Created DATETIME(6) NOT NULL
            );"""
        member_query = """CREATE TABLE IF NOT EXISTS Member (
            UserID INTEGER NOT NULL,
            RoomID INTEGER NOT NULL,
            UNIQUE(UserID, RoomID)
            );"""
        message_query = """CREATE TABLE IF NOT EXISTS Message (
            MessageID INTEGER PRIMARY KEY,
            RoomID INTEGER NOT NULL,
            UserID INTEGER NOT NULL,
            Text TEXT NOT NULL,
            Date_Sent INTEGER NOT NULL
            );"""
        with self.connection() as conn:
            self.execute_query(conn, user_query)
            self.execute_query(conn, group_query)
            self.execute_query(conn, member_query)
            self.execute_query(conn, message_query)
            # Add the root user if they don't exist yet
            try:
                self.get_user_id_by_name(conn, "root")
            except ItemNotFoundException:
                self.new_user("root", "root", '')
            # Create the default group if there are no groups in the DB
            if len(self.group_names()) == 0:
                logging.info("Creating default group.")
                self.new_group("default")

    def new_message(self, group_name: str, user_name: str, text: str, time_sent: datetime) -> int:
        """Create a new message row."""
        create_msg = "INSERT INTO Message (RoomID, UserID, Text, Date_Sent) VALUES (?, ?, ?, ?);"""
        with self.connection() as con:
            # Find the associated group ID
            room_id = self.get_room_id_by_name(con, group_name)
            user_id = self.get_user_id_by_name(con, user_name)
            cursor = self.execute_query(
                con, create_msg, (room_id, user_id, text, time_sent))
            m_id = cursor.lastrowid
            logging.debug(f"Saved message {m_id}")
            return m_id

    def new_group(self, group_name: str, user_name: str = None, group_password: str = None) -> int:
        """Create a new group row."""
        create_room = "INSERT INTO Room (Name, Password, Date_Created) VALUES (?, ?, ?);"
        with self.connection() as con:
            cur = self.execute_query(con, create_room, (group_name, group_password, datetime.now()))
            group_id = cur.lastrowid
            if user_name is not None:
                self.new_member(user_name, group_name)
            return group_id

    def new_member(self, user_name: str, group_name: str) -> int:
        """Create a new member row."""
        query = "INSERT INTO Member (UserID, RoomID) VALUES (?, ?);"
        with self.connection() as con:
            user_id = self.get_user_id_by_name(con, user_name)
            group_id = self.get_room_id_by_name(con, group_name)
            cur = self.execute_query(con, query, (user_id, group_id))
            return cur.lastrowid

    def new_user(self, user_name: str, password: str, address: str) -> bool:
        """Create a new user row. Returns true if created new user."""
        query = "SELECT Username FROM User WHERE Username = ? LIMIT 1;"
        with self.connection() as con:
            result = self.read_query(con, query, (user_name,))
        if len(result) == 0:
            pwrd_salt, pwrd_hash = self.hash_new_password(password)
            pwd_hashed = f"{pwrd_salt}${pwrd_hash}"
            query2 = "INSERT INTO User (Address, Username, Password) VALUES (?, ?, ?);"
            with self.connection() as con:
                self.execute_query(con, query2, (address, user_name, pwd_hashed))
            return True
        return False

    def user_login(self, user_name: str, password: str, addr: Tuple) -> str:
        """Attempt to log in user"""
        with self.connection() as con:
            correct_password = self.verify_user_credentials(con, user_name, password)
            if correct_password:
                # Update this user's associated IP address if they enter the correct password
                self.update_user_address(con, user_name, addr)
        return correct_password

    def message_history(self, room_name: str) -> Dict:
        """Return message history as a list of dictionaries."""
        with self.connection() as con:
            room_id = self.get_room_id_by_name(con, room_name)
            query = """
            SELECT User.Username, Message.Text, datetime(Message.Date_Sent)
            FROM Message INNER JOIN User
            ON Message.UserID = User.UserID
            WHERE Message.RoomID = ?;"""
            for r in self.read_query(con, query, (room_id,)):
                yield {
                    "Username": r[0],
                    "Text": r[1],
                    "Date_Sent": r[2],
                }

    def group_history(self, user_name: str) -> Dict:
        """Return message history as a list of dictionaries."""
        with self.connection() as con:
            user_id = self.get_user_id_by_name(con, user_name)
            query = """
            SELECT Room.Name, datetime(Room.Date_Created)
            FROM Room INNER JOIN Member
            ON Room.RoomID = Member.RoomID
            WHERE Member.UserID = ?;"""
            for r in self.read_query(con, query, (user_id,)):
                yield {
                    "Name": r[0],
                    "Date_Created": r[1],
                }

    def group_names(self) -> List[str]:
        """Return all group names."""
        query = "SELECT Name FROM Room;"
        with self.connection() as con:
            results = self.read_query(con, query)
            return [r[0] for r in results]

    def connection(self) -> sqlite3.Connection:
        """Open a new connection to the database, or log an error."""
        c = None
        try:
            c = sqlite3.connect(self.db_name)
        except Error as err:
            logging.error(f"Connection error: '{err}'")
        return c

    def execute_query(self, c: sqlite3.Connection, query: str, values: List=None) -> sqlite3.Cursor:
        """Execute and commit a query to the database."""
        cursor: sqlite3.Cursor = c.cursor()
        if values is not None:
            cursor.execute(query, values)
        else:
            cursor.execute(query)
        c.commit()
        return cursor   

    def read_query(self, c: sqlite3.Connection, query: str, values: List=None, **kwargs) -> List[Tuple]:
        """Fetch all results from a query, or log an error."""
        cursor: sqlite3.Cursor = c.cursor(**kwargs)
        cursor.execute(query, values or [])
        return cursor.fetchall()

    def get_user_id_by_name(self, c: sqlite3.Connection, user_name: str) -> int:
        """Return a user row by user ID."""
        find_user_query = "SELECT UserID FROM User WHERE Username = ? LIMIT 1;"
        user_row = self.read_query(c, find_user_query, (user_name,))
        if len(user_row) == 0:
            raise ItemNotFoundException(f"No User with name '{user_name}'")
        return user_row[0][0]

    def get_room_id_by_name(self, c: sqlite3.Connection, room_name: str) -> int:
        """Return a room row by room ID."""
        find_user_query = "SELECT RoomID FROM Room WHERE Name = ? LIMIT 1;"
        room_row = self.read_query(c, find_user_query, (room_name,))
        if len(room_row) == 0:
            raise ItemNotFoundException(f"No Room with name '{room_name}'")
        return room_row[0][0]

    def verify_user_credentials(self, c: sqlite3.Connection, user_name: str, password: str) -> bool:
        """Return user ID if credentials are valid."""
        verify_user_query = "SELECT Username, Password FROM User WHERE Username = ? LIMIT 1;"
        user_row = self.read_query(c, verify_user_query, (user_name,))
        if len(user_row) == 0:
            raise ItemNotFoundException(f"No User with name '{user_name}', and password '{password}'")
        hashed_pwrd: str = user_row[0][1]
        salt, hash = hashed_pwrd.split("$")
        return self.is_correct_password(salt, hash, password)

    def get_addresses_for_group(self, group_name: str) -> List[Tuple]:
        """Return a list of addresses for a group."""
        get_addresses_query = """
            SELECT User.Address
            FROM Room INNER JOIN Member
            ON Room.RoomID = Member.RoomID
            INNER JOIN User
            ON Member.UserID = User.UserID
            WHERE Room.Name = ?;"""
        with self.connection() as c:
            str_addresses = self.read_query(c, get_addresses_query, (group_name,))
            tuple_addresses = []
            for str_addr in str_addresses:
                result = urllib.parse.urlsplit('//' + str_addr[0])
                if result.hostname is not None and result.port is not None:
                    tuple_addresses.append((result.hostname, result.port))
        return tuple_addresses

    def update_user_address(self, con: sqlite3.Connection, username: str, addr: tuple) -> None:
        """Update a user's last seen IP address and port."""
        query = "UPDATE User SET Address=? WHERE Username=?;"
        str_addr = f"{addr[0]}:{addr[1]}"
        self.execute_query(con, query, (str_addr, username))

    def user_list(self):
        """Fetch a list of users from the database."""
        user_list_query = "SELECT User.Username FROM User"
        with self.connection() as c:
            return [i[0] for i in self.read_query(c, user_list_query)]

    def hash_new_password(self, password: str) -> Tuple[str, str]:
        """
        Hash the provided password with a randomly-generated salt and return the
        salt and hash to store in the database.

        Adapted from https://stackoverflow.com/questions/9594125/salt-and-hash-a-password-in-python
        """
        salt = os.urandom(16)
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return base64.encodebytes(salt).decode("utf-8"), base64.encodebytes(pw_hash).decode("utf-8")

    def is_correct_password(self, salt: str, pw_hash: str, password: str) -> bool:
        """
        Given a previously-stored salt and hash, and a password provided by a user
        trying to log in, check whether the password is correct.

        Adapted from https://stackoverflow.com/questions/9594125/salt-and-hash-a-password-in-python
        """
        salt_bytes, hash_bytes = base64.b64decode(salt), base64.b64decode(pw_hash)
        return hmac.compare_digest(
            hash_bytes,
            hashlib.pbkdf2_hmac('sha256', password.encode(), salt_bytes, 100000)
        )