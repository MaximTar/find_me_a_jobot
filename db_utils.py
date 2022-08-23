import sqlite3

import config
from dicts import UserQuery, UserTextQuery

# str(v.__name__).upper()
QUERY_FIELDS = {str(k).upper(): 'TEXT' for k in UserQuery.__annotations__.keys()}  # for table creation
TEXT_QUERY_FIELDS = {str(k).upper(): 'TEXT' for k in UserTextQuery.__annotations__.keys()}  # for table creation


# TODO logging, tries
def create_connection(db_file):
    try:
        connection = sqlite3.connect(db_file)
        return connection
    except sqlite3.Error:  # as e:
        # logging
        pass


def create_table(connection, table_name, fields, pk_fields=None, surrogate_pk=None):
    if pk_fields:
        connection.cursor().execute(f"CREATE TABLE IF NOT EXISTS {table_name} "
                                    f"({', '.join([f'{k} {v}' for k, v in fields.items()])}, "
                                    f"PRIMARY KEY ({', '.join(map(str, pk_fields))}))")
    elif surrogate_pk:
        # surrogate primary key
        connection.cursor().execute(f"CREATE TABLE IF NOT EXISTS {table_name} "
                                    f"(ID INTEGER PRIMARY KEY, "
                                    f"{', '.join([f'{k} {v}' for k, v in fields.items()])})")
    else:
        # composite primary key
        connection.cursor().execute(f"CREATE TABLE IF NOT EXISTS {table_name} "
                                    f"({', '.join([f'{k} {v}' for k, v in fields.items()])}, "
                                    f"PRIMARY KEY ({', '.join(map(str, fields.keys()))}))")
    connection.commit()


def insert_from_list(connection, table_name, values, fields=None, surrogate_pk=False):
    if fields is None:
        if surrogate_pk:
            connection.cursor().execute(f"INSERT INTO {table_name} VALUES (NULL, {repr(tuple(map(str, values)))[1:]})")
        else:
            connection.cursor().execute(f"INSERT INTO {table_name} VALUES {repr(tuple(map(str, values)))}")
    else:
        connection.cursor().execute(
            f"INSERT INTO {table_name} ({', '.join(map(str, fields))}) VALUES {repr(tuple(map(str, values)))}")
    connection.commit()


def insert_from_dict(connection, table_name, inserted_dict):
    columns, values = tuple(map(str, inserted_dict.keys())), tuple(map(str, inserted_dict.values()))
    connection.cursor().execute(f"INSERT INTO {table_name} {repr(columns)} VALUES {repr(values)}")
    connection.commit()


def delete(connection, table_name, condition):
    connection.cursor().execute(f"DELETE FROM {table_name} WHERE {condition}")
    connection.commit()


def simple_select(connection, table_name, columns, condition=True):
    cursor = connection.cursor()
    cursor.execute(f"SELECT {columns} FROM {table_name} WHERE {condition}")
    return cursor.fetchall()


def update_from_list(connection, table_name, columns, values, condition):
    connection.cursor().execute(
        f"UPDATE {table_name} "
        f"SET {', '.join([f'{c} = {repr(str(v))}' for c, v in zip(columns, values)])} "
        f"WHERE {condition}")
    connection.commit()


def update_from_dict(connection, table_name, updated_dict, condition):
    connection.cursor().execute(
        f"UPDATE {table_name} "
        f"SET {', '.join([f'{c} = {repr(str(v))}' for c, v in updated_dict.items()])} "
        f"WHERE {condition}")
    connection.commit()


conn = create_connection(config.DB_NAME)
create_table(conn, config.QUERIES_TABLE_NAME, QUERY_FIELDS)
try:
    conn.cursor().execute(f"ALTER TABLE {config.QUERIES_TABLE_NAME} ADD COLUMN COUNTER")
    conn.commit()
except sqlite3.OperationalError:
    pass
create_table(conn, config.TEXT_QUERIES_TABLE_NAME, TEXT_QUERY_FIELDS)
conn.close()
