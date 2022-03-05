from audioop import add
from importlib.resources import path
from typing import Dict, List, Tuple
from datetime import datetime
from exceptions import ItemNotFoundException
import sqlite3
from sqlite3 import Error
import logging

class DatabaseController():

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
            RoomID INTEGER NOT NULL
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

    def new_message(self, group_name: str, user_name: str, text: str):
        """Create a new message row."""
        create_msg = "INSERT INTO Message (RoomID, UserID, Text, Date_Sent) VALUES (?, ?, ?, ?);"""
        with self.connection() as con:
            # Find the associated group ID
            room_id = self.get_room_id_by_name(con, group_name)
            user_id = self.get_user_id_by_name(con, user_name)
            cursor = self.execute_query(
                con, create_msg, [(room_id, user_id, text, datetime.now())])
            m_id = cursor.lastrowid
            logging.debug(f"Saved message {m_id}")

    def new_group(self, group_name: str, user_name: str = None, group_password: str = None) -> int:
        """Create a new group row."""
        create_room = "INSERT INTO Room (Name, Password, Date_Created) VALUES (?, ?, ?);"
        with self.connection() as con:
            if user_name:
                user_id = self.get_user_id_by_name(con, user_name)
            cur = self.execute_query(con, create_room, [(group_name, group_password, datetime.now())])
            group_id = cur.lastrowid
            if user_name:
                self.new_member(user_id, group_id)
            return group_id

    def new_member(self, user_id: int, group_id: int) -> int:
        """Create a new member row."""
        query = "INSERT INTO Member (UserID, RoomID) VALUES (?, ?);"
        with self.connection() as con:
            cur = self.execute_query(con, query, [(user_id, group_id)])
            return cur.lastrowid

    def new_user(self, user_name: str, password: str, address: str) -> int:
        """Create a new user row."""
        query = "INSERT INTO User (Address, Username, Password) VALUES (?, ?, ?);"
        with self.connection() as con:
            cur = self.execute_query(con, query, [(address, user_name, password)])
            return cur.lastrowid

    def user_login(self, user_name: str, password: str) -> int:
        """Attempt to log in user"""
        with self.connection() as con:
            result = self.verify_user_credentials(con, user_name, password)
        return result

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
            cursor.executemany(query, values)
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

    def verify_user_credentials(self, c: sqlite3.Connection, user_name: str, password: str) -> int:
        """Return user ID if credentials are valid."""
        verify_user_query = "SELECT UserID FROM User WHERE Username = ? AND Password = ? LIMIT 1;"
        user_row = self.read_query(c, verify_user_query, (user_name, password))
        if len(user_row) == 0:
            raise ItemNotFoundException(f"No User with name '{user_name}', and password '{password}'")
        return user_row[0][0]