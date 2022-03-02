import mysql.connector
from mysql.connector import Error
from datetime import datetime

class DatabaseController():

    def __init__(self, pswd, db_name):
        connection = self.create_database_connection("localhost", "root", pswd, db_name)
        self.create_database(connection, "CREATE DATABASE "+db_name)
        user_query = """CREATE TABLE USER (
            User_Address VARCHAR(50) PRIMARY KEY,
            Username VARCHAR(50)  NOT NULL,
            Password VARCHAR(50)  NOT NULL
            );"""
        group_query = """CREATE TABLE Group (
            GroupID VARCHAR(50) PRIMARY KEY,
            Name VARCHAR(50)  NOT NULL,
            Password VARCHAR(50)  NOT NULL,
            Date_Created DATETIME(50) NOT NULL
            );"""
        member_query = """CREATE TABLE Member (
            Member_Address VARCHAR(50) NOT NULL,
            GroupID VARCHAR(50)  NOT NULL
            );"""
        message_query = """CREATE TABLE Message (
            MessageID VARCHAR(50) PRIMARY KEY,
            GroupID VARCHAR(50)  NOT NULL,
            Content VARCHAR(50) NOT NULL,
            User_Address VARCHAR(50)  NOT NULL,
            Date_Sent DATETIME(50) NOT NULL
            );"""
        self.execute_query(connection, user_query)
        self.execute_query(connection, group_query)
        self.execute_query(connection, member_query)
        self.execute_query(connection, message_query)

    def new_message(self, msg, user_address: str, groupID, pswd, db_name):
        connection = self.create_database_connection("localhost", "root", pswd, db_name)

        total_messages = str(self.read_query(connection, "SELECT COUNT(MessageID) FROM Message;"))
        total_messages = total_messages[1:len(total_messages)]

        query = """INSERT INTO Message 
            VALUES ('M"""+total_messages+"""', '"""+groupID+"""', '"""+msg+"""', '"""+user_address+"""', """+datetime.now()+"""); """
        self.execute_query(connection, query)

    def new_group(self, user_address, group_name, group_password, db_pswd, db_name):
        connection = self.create_database_connection("localhost", "root", db_pswd, db_name)

        total_groups = str(self.read_query(connection, "SELECT COUNT(GroupID) FROM Group;"))
        total_groups = total_groups[1:len(total_groups)]

        query = """INSERT INTO Group
            VALUES ('G"""+total_groups+"""', '"""+group_name+"""', '"""+group_password+"""', """+datetime.now()+"""); """
        self.execute_query(connection, query)

    def new_member(self, user_address, groupID, db_pswd, db_name):
        connection = self.create_database_connection("localhost", "root", db_pswd, db_name)

        query = """INSERT INTO Member
            VALUES ('"""+user_address+"""', '"""+groupID+"""');"""
        self.execute_query(connection, query)

    def message_history(self, groupID, db_pswd, db_name):
        connection = self.create_database_connection("localhost", "root", db_pswd, db_name)

        query = f"""SELECT Content FROM Message
            WHERE GroupID = '{groupID}';"""
        results = self.read_query(connection, query)
        
        msg_list = []
        for msg in results:
            msg = str(msg)
            msg = msg[1:len(msg)]
            msg_list.append(msg)

        return msg_list

    def group_names(self, db_pswd, db_name):
        connection = self.create_database_connection("localhost", "root", db_pswd, db_name)

        query = """SELECT Name FROM Group;"""
        results = self.read_query(connection, query)

        group_list = []
        for name in results:
            name = str(name)
            name = name[1:len(name)]
            group_list

    def create_database(self, connection, query):
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            print("Successfully created Database.")
        except Error as err:
            print(f"Error: '{err}'")
            

    def create_database_connection(self, host_name, username, password, database_name):
        connection = None
        try:
            connection = mysql.connector.connect(
                host=host_name,
                user=username,
                passwd=password,
                database=database_name
            )
            print("Successful connection to MySQL Database.")
        except Error as err:
            print(f"Error: '{err}'")
        return connection

    def execute_query(self, connection, query):
        cursor = connection.cursor()
        try:
            cursor.execute(query)
            connection.commit()
            print("Query successful.")
            return True
        except Error as err:
            print(f"Error: '{err}'")
            return False

    def read_query(self, connection, query):
        cursor = connection.cursor()
        result = None
        try:
            cursor.execute(query)
            result = cursor.fetchall()
            return result
        except Error as err:
            print(f"Error: '{err}'")

    

    