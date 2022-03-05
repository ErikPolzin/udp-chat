from typing import Dict, List, Tuple
import mysql.connector
from mysql.connector import Error, MySQLConnection
from mysql.connector.cursor import MySQLCursor
from datetime import datetime
from exceptions import ItemNotFoundException
import logging

class DatabaseController():

    def __init__(
            self,
            db_name: str,
            pswd: str,
            host: str = "localhost",
            user: str = "root"):
        """Create a new database controller with given parameters."""

        # Controller constants
        self.host = host
        self.pswd = pswd
        self.db_name = db_name
        self.user = user

        # Create the database if it doesn't exist
        self.create_database(db_name)
        user_query = """CREATE TABLE IF NOT EXISTS User (
            UserID INT AUTO_INCREMENT PRIMARY KEY,
            Address VARCHAR(50),
            Username VARCHAR(50)  NOT NULL UNIQUE,
            Password VARCHAR(50)  NOT NULL
            );"""
        group_query = """CREATE TABLE IF NOT EXISTS Room (
            RoomID INT AUTO_INCREMENT PRIMARY KEY,
            Name VARCHAR(50)  NOT NULL UNIQUE,
            Password VARCHAR(50),
            Date_Created DATETIME(6) NOT NULL
            );"""
        member_query = """CREATE TABLE IF NOT EXISTS Member (
            UserID INT NOT NULL,
            RoomID INT NOT NULL
            );"""
        message_query = """CREATE TABLE IF NOT EXISTS Message (
            MessageID INT AUTO_INCREMENT PRIMARY KEY,
            RoomID INT NOT NULL,
            UserID INT NOT NULL,
            Text VARCHAR(50) NOT NULL,
            Date_Sent DATETIME(6) NOT NULL
            );"""
        with self.connection() as conn:
            self.execute_query(conn, user_query)
            self.execute_query(conn, group_query)
            self.execute_query(conn, member_query)
            self.execute_query(conn, message_query)
            # Create the default group if there are no groups in the DB
            if len(self.group_names()) == 0:
                logging.info("Creating default group.")
                self.new_group("default")

    def new_message(self, group_name: str, user_name: str, text: str):
        """Create a new message row."""
        create_msg = "INSERT INTO Message (RoomID, UserID, Text, Date_Sent) VALUES (%s, %s, %s, %s);"""
        with self.connection() as con:
            # Find the associated group ID
            room_id = self.get_room_id_by_name(con, group_name)
            user_id = self.get_user_id_by_name(con, user_name)
            cursor = self.execute_query(
                con, create_msg, [(room_id, user_id, text, datetime.now())])
            m_id = cursor.lastrowid
            logging.debug(f"Saved message {m_id}")

    def new_group(self, group_name: str, user_name: str, group_password: str = None) -> int:
        """Create a new group row."""
        create_room = "INSERT INTO Room (Name, Password, Date_Created) VALUES (%s, %s, %s);"
        with self.connection() as con:
            user_id = self.get_user_id_by_name(con, user_name)
            cur = self.execute_query(con, create_room, [(group_name, group_password, datetime.now())])
            group_id = cur.lastrowid
            self.new_member(user_id, group_id)
            return group_id

    def new_member(self, user_id: int, group_id: int) -> int:
        """Create a new member row."""
        query = "INSERT INTO Member (UserID, RoomID) VALUES (%s, %s);"
        with self.connection() as con:
            cur = self.execute_query(con, query, [(user_id, group_id)])
            return cur.lastrowid

    def message_history(self, room_name: str) -> Dict:
        """Return message history as a list of dictionaries."""
        with self.connection() as con:
            room_id = self.get_room_id_by_name(con, room_name)
            query = """
            SELECT User.Username, Message.Text, Message.Date_Sent
            FROM Message INNER JOIN User
            ON Message.UserID = User.UserID
            WHERE Message.RoomID = '%s';""" % (room_id,)
            return self.read_query(con, query, dictionary=True)

    def group_names(self) -> List[str]:
        """Return all group names."""
        query = "SELECT Name FROM Room;"
        with self.connection() as con:
            results = self.read_query(con, query)
            return [r[0] for r in results]

    def create_database(self, db_name: str):
        """Create a database with a given database name."""
        query = "CREATE DATABASE IF NOT EXISTS "+db_name
        con = mysql.connector.connect(
                host=self.host,
                user=self.user,
                passwd=self.pswd,
            )
        cursor: MySQLCursor = con.cursor()
        try:
            cursor.execute(query)
        except Error as err:
            logging.error(f"Error creating database: '{err}'")
        con.close()
        return cursor

    def connection(
            self,
            host=None,
            user=None,
            password=None,
            database_name=None
            ) -> MySQLConnection:
        """Open a new connection to the database, or log an error."""
        c = None
        try:
            c = mysql.connector.connect(
                host=host or self.host,
                user=user or self.user,
                passwd=password or self.pswd,
                database=database_name or self.db_name
            )
        except Error as err:
            logging.error(f"Connection error: '{err}'")
        return c

    def execute_query(self, c: MySQLConnection, query: str, values: List=None) -> MySQLCursor:
        """Execute and commit a query to the database."""
        cursor: MySQLCursor = c.cursor()
        if values is not None:
            cursor.executemany(query, values)
        else:
            cursor.execute(query)
        c.commit()
        return cursor

    def read_query(self, c: MySQLConnection, query: str, **kwargs) -> List[Tuple]:
        """Fetch all results from a query, or log an error."""
        cursor: MySQLCursor = c.cursor(**kwargs)
        cursor.execute(query)
        return cursor.fetchall()

    def get_user_id_by_name(self, c: MySQLConnection, user_name: str) -> int:
        """Return a user row by user ID."""
        find_user_query = "SELECT UserID FROM User WHERE Username = '%s' LIMIT 1;" % (user_name,)
        user_row = self.read_query(c, find_user_query)
        if len(user_row) == 0:
            raise ItemNotFoundException(f"No User with name '{user_name}'")
        return user_row[0][0]

    def get_room_id_by_name(self, c: MySQLConnection, room_name: str) -> int:
        """Return a room row by room ID."""
        find_user_query = "SELECT RoomID FROM Room WHERE Name = '%s' LIMIT 1;" % (room_name,)
        room_row = self.read_query(c, find_user_query)
        if len(room_row) == 0:
            raise ItemNotFoundException(f"No Room with name '{room_name}'")
        return room_row[0][0]

    

    