"""
Project package init.

We use PyMySQL on hosting environments where compiling mysqlclient is hard.
This makes Django treat PyMySQL as MySQLdb.
"""

import pymysql

pymysql.install_as_MySQLdb()
