# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import copy
import os
import unittest

from trac.config import ConfigurationError
from trac.db.api import DatabaseManager, get_column_names, \
                        parse_connection_uri
from trac.db_default import (schema as default_schema,
                             db_version as default_db_version)
from trac.db.schema import Column, Table
from trac.test import EnvironmentStub, get_dburi


class ParseConnectionStringTestCase(unittest.TestCase):

    def test_sqlite_relative(self):
        # Default syntax for specifying DB path relative to the environment
        # directory
        self.assertEqual(('sqlite', {'path': 'db/trac.db'}),
                         parse_connection_uri('sqlite:db/trac.db'))

    def test_sqlite_absolute(self):
        # Standard syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         parse_connection_uri('sqlite:///var/db/trac.db'))
        # Legacy syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         parse_connection_uri('sqlite:/var/db/trac.db'))

    def test_sqlite_with_timeout_param(self):
        # In-memory database
        self.assertEqual(('sqlite', {'path': 'db/trac.db',
                                     'params': {'timeout': '10000'}}),
                         parse_connection_uri('sqlite:db/trac.db?timeout=10000'))

    def test_sqlite_windows_path(self):
        # In-memory database
        os_name = os.name
        try:
            os.name = 'nt'
            self.assertEqual(('sqlite', {'path': 'C:/project/db/trac.db'}),
                             parse_connection_uri('sqlite:C|/project/db/trac.db'))
        finally:
            os.name = os_name

    def test_postgres_simple(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'path': '/trac'}),
                         parse_connection_uri('postgres://localhost/trac'))

    def test_postgres_with_port(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                         parse_connection_uri('postgres://localhost:9431/trac'))

    def test_postgres_with_creds(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': 'letmein',
                                       'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                 parse_connection_uri('postgres://john:letmein@localhost:9431/trac'))

    def test_postgres_with_quoted_password(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': ':@/',
                                       'host': 'localhost', 'path': '/trac'}),
                     parse_connection_uri('postgres://john:%3a%40%2f@localhost/trac'))

    def test_mysql_simple(self):
        self.assertEqual(('mysql', {'host': 'localhost', 'path': '/trac'}),
                     parse_connection_uri('mysql://localhost/trac'))

    def test_mysql_with_creds(self):
        self.assertEqual(('mysql', {'user': 'john', 'password': 'letmein',
                                    'host': 'localhost', 'port': 3306,
                                    'path': '/trac'}),
                     parse_connection_uri('mysql://john:letmein@localhost:3306/trac'))

    def test_empty_string(self):
        self.assertRaises(ConfigurationError, parse_connection_uri, '')

    def test_invalid_port(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
                          'postgres://localhost:42:42')

    def test_invalid_schema(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
                          'sqlitedb/trac.db')

    def test_no_path(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
                          'sqlite:')

    def test_invalid_query_string(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
                          'postgres://localhost/schema?name')


class StringsTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_insert_unicode(self):
        with self.env.db_transaction as db:
            quoted = db.quote('system')
            db("INSERT INTO " + quoted + " (name,value) VALUES (%s,%s)",
               ('test-unicode', u'ünicöde'))
        self.assertEqual([(u'ünicöde',)], self.env.db_query(
            "SELECT value FROM " + quoted + " WHERE name='test-unicode'"))

    def test_insert_empty(self):
        from trac.util.text import empty
        with self.env.db_transaction as db:
            quoted = db.quote('system')
            db("INSERT INTO " + quoted + " (name,value) VALUES (%s,%s)",
               ('test-empty', empty))
        self.assertEqual([(u'',)], self.env.db_query(
            "SELECT value FROM " + quoted + " WHERE name='test-empty'"))

    def test_insert_markup(self):
        from trac.util.html import Markup
        with self.env.db_transaction as db:
            quoted = db.quote('system')
            db("INSERT INTO " + quoted + " (name,value) VALUES (%s,%s)",
               ('test-markup', Markup(u'<em>märkup</em>')))
        self.assertEqual([(u'<em>märkup</em>',)], self.env.db_query(
            "SELECT value FROM " + quoted + " WHERE name='test-markup'"))

    def test_quote(self):
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute('SELECT 1 AS %s' %
                           db.quote(r'alpha\`\"\'\\beta``gamma""delta'))
            self.assertEqual(r'alpha\`\"\'\\beta``gamma""delta',
                             get_column_names(cursor)[0])

    def test_quoted_id_with_percent(self):
        name = """%?`%s"%'%%"""

        def test(logging=False):
            with self.env.db_query as db:
                cursor = db.cursor()
                if logging:
                    cursor.log = self.env.log

                cursor.execute('SELECT 1 AS ' + db.quote(name))
                self.assertEqual(name, get_column_names(cursor)[0])
                cursor.execute('SELECT %s AS ' + db.quote(name), (42,))
                self.assertEqual(name, get_column_names(cursor)[0])
                stmt = """
                    UPDATE {0} SET value=%s WHERE 1=(SELECT 0 AS {1})
                    """.format(db.quote('system'), db.quote(name))
                cursor.executemany(stmt, [])
                cursor.executemany(stmt, [('42',), ('43',)])

        test()
        test(True)

    def test_prefix_match_case_sensitive(self):
        with self.env.db_transaction as db:
            db.executemany("""
                INSERT INTO {0} (name,value) VALUES (%s,1)
                """.format(db.quote('system')),
                [('blahblah',), ('BlahBlah',), ('BLAHBLAH',), (u'BlähBlah',),
                 (u'BlahBläh',)])

        with self.env.db_query as db:
            names = sorted(name for name, in db(
                "SELECT name FROM {0} WHERE name {1}"
                .format(db.quote('system'), db.prefix_match()),
                (db.prefix_match_value('Blah'),)))
        self.assertEqual('BlahBlah', names[0])
        self.assertEqual(u'BlahBläh', names[1])
        self.assertEqual(2, len(names))

    def test_prefix_match_metachars(self):
        def do_query(prefix):
            with self.env.db_query as db:
                return [name for name, in db("""
                    SELECT name FROM {0} WHERE name {1} ORDER BY name
                    """.format(db.quote('system'), db.prefix_match()),
                    (db.prefix_match_value(prefix),))]

        values = ['foo*bar', 'foo*bar!', 'foo?bar', 'foo?bar!',
                  'foo[bar', 'foo[bar!', 'foo]bar', 'foo]bar!',
                  'foo%bar', 'foo%bar!', 'foo_bar', 'foo_bar!',
                  'foo/bar', 'foo/bar!', 'fo*ob?ar[fo]ob%ar_fo/obar']
        with self.env.db_transaction as db:
            db.executemany("""
                INSERT INTO {0} (name,value) VALUES (%s,1)
                """.format(db.quote('system')),
                [(value,) for value in values])

        self.assertEqual(['foo*bar', 'foo*bar!'], do_query('foo*'))
        self.assertEqual(['foo?bar', 'foo?bar!'], do_query('foo?'))
        self.assertEqual(['foo[bar', 'foo[bar!'], do_query('foo['))
        self.assertEqual(['foo]bar', 'foo]bar!'], do_query('foo]'))
        self.assertEqual(['foo%bar', 'foo%bar!'], do_query('foo%'))
        self.assertEqual(['foo_bar', 'foo_bar!'], do_query('foo_'))
        self.assertEqual(['foo/bar', 'foo/bar!'], do_query('foo/'))
        self.assertEqual(['fo*ob?ar[fo]ob%ar_fo/obar'], do_query('fo*'))
        self.assertEqual(['fo*ob?ar[fo]ob%ar_fo/obar'],
                         do_query('fo*ob?ar[fo]ob%ar_fo/obar'))


class ConnectionTestCase(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()
        self.schema = [
            Table('HOURS', key='ID')[
                Column('ID', auto_increment=True),
                Column('AUTHOR')
            ],
            Table('blog', key='bid')[
                Column('bid', auto_increment=True),
                Column('author'),
                Column('comment')
            ]
        ]
        self.dbm = DatabaseManager(self.env)
        self.dbm.drop_tables(self.schema)
        self.dbm.create_tables(self.schema)

    def tearDown(self):
        DatabaseManager(self.env).drop_tables(self.schema)
        self.env.reset_db()

    def test_drop_column(self):
        """Data is preserved when column is dropped."""
        table_data = [
            ('blog', ('author', 'comment'),
             (('author1', 'comment one'),
              ('author2', 'comment two'))),
        ]
        self.dbm.insert_into_tables(table_data)

        with self.env.db_transaction as db:
            db.drop_column('blog', 'comment')

        data = list(self.env.db_query("SELECT * FROM blog"))
        self.assertEqual((1, 'author1'), data[0])
        self.assertEqual((2, 'author2'), data[1])

    def test_drop_column_no_exists(self):
        """Error is not raised when dropping non-existent column."""
        table_data = [
            ('blog', ('author', 'comment'),
             (('author1', 'comment one'),
              ('author2', 'comment two'))),
        ]
        self.dbm.insert_into_tables(table_data)

        with self.env.db_transaction as db:
            db.drop_column('blog', 'tags')

        data = list(self.env.db_query("SELECT * FROM blog"))
        self.assertEqual((1, 'author1', 'comment one'), data[0])
        self.assertEqual((2, 'author2', 'comment two'), data[1])

    def test_rollback_transaction_on_exception(self):
        """Transaction is rolled back when an exception occurs in the
        transaction context manager.
        """
        insert_sql = "INSERT INTO blog (bid, author) VALUES (42, 'anonymous')"
        try:
            with self.env.db_transaction as db:
                db(insert_sql)
                db(insert_sql)
        except self.env.db_exc.IntegrityError:
            pass

        for _, in self.env.db_query("""
                SELECT author FROM blog WHERE bid=42
                """):
            self.fail("Transaction was not rolled back")

    def test_rollback_nested_transaction_on_exception(self):
        """Transaction is rolled back when an exception occurs in the
        inner transaction context manager.
        """
        sql = "INSERT INTO blog (bid, author) VALUES (42, 'anonymous')"
        try:
            with self.env.db_transaction as db_outer:
                db_outer(sql)
                with self.env.db_transaction as db_inner:
                    db_inner(sql)
        except self.env.db_exc.IntegrityError:
            pass

        for _, in self.env.db_query("""
                SELECT author FROM blog WHERE bid=42
                """):
            self.fail("Transaction was not rolled back")

    def test_get_last_id(self):
        q = "INSERT INTO report (author) VALUES ('anonymous')"
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(q)
            # Row ID correct before...
            id1 = db.get_last_id(cursor, 'report')
            db.commit()
            cursor.execute(q)
            # ... and after commit()
            db.commit()
            id2 = db.get_last_id(cursor, 'report')

        self.assertNotEqual(0, id1)
        self.assertEqual(id1 + 1, id2)

    def test_update_sequence_default_column_name(self):
        with self.env.db_transaction as db:
            db("INSERT INTO report (id, author) VALUES (42, 'anonymous')")
            cursor = db.cursor()
            db.update_sequence(cursor, 'report')

        self.env.db_transaction(
            "INSERT INTO report (author) VALUES ('next-id')")

        self.assertEqual(43, self.env.db_query(
                "SELECT id FROM report WHERE author='next-id'")[0][0])

    def test_update_sequence_nondefault_column_name(self):
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO blog (bid, author) VALUES (42, 'anonymous')")
            db.update_sequence(cursor, 'blog', 'bid')

        self.env.db_transaction(
            "INSERT INTO blog (author) VALUES ('next-id')")

        self.assertEqual(43, self.env.db_query(
            "SELECT bid FROM blog WHERE author='next-id'")[0][0])

    def test_identifiers_need_quoting(self):
        """Test for regression described in comment:4:ticket:11512."""
        with self.env.db_transaction as db:
            db("INSERT INTO %s (%s, %s) VALUES (42, 'anonymous')"
               % (db.quote('HOURS'), db.quote('ID'), db.quote('AUTHOR')))
            cursor = db.cursor()
            db.update_sequence(cursor, 'HOURS', 'ID')

        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO %s (%s) VALUES ('next-id')"
                % (db.quote('HOURS'), db.quote('AUTHOR')))
            last_id = db.get_last_id(cursor, 'HOURS', 'ID')

        self.assertEqual(43, last_id)

    def test_get_table_names(self):
        schema = default_schema + self.schema
        with self.env.db_query as db:
            # Some DB (e.g. MariaDB) normalize the table names to lower case
            self.assertEqual(
                sorted(table.name.lower() for table in schema),
                sorted(name.lower() for name in db.get_table_names()))

    def test_get_column_names(self):
        schema = default_schema + self.schema
        with self.env.db_query as db:
            for table in schema:
                column_names = [col.name for col in table.columns]
                self.assertEqual(column_names,
                                 db.get_column_names(table.name))

    def test_get_column_names_non_existent_table(self):
        with self.assertRaises(self.env.db_exc.OperationalError) as cm:
            self.dbm.get_column_names('blah')
        self.assertIn(unicode(cm.exception), ('Table "blah" not found',
                                              'Table `blah` not found'))


class DatabaseManagerTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.dbm = DatabaseManager(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_destroy_db(self):
        """Database doesn't exist after calling destroy_db."""
        with self.env.db_query as db:
            db("SELECT name FROM " + db.quote('system'))
        self.assertIsNotNone(self.dbm._cnx_pool)
        self.dbm.destroy_db()
        self.assertIsNone(self.dbm._cnx_pool)  # No connection pool
        scheme, params = parse_connection_uri(get_dburi())
        if scheme != 'postgres' or params.get('schema', 'public') != 'public':
            self.assertFalse(self.dbm.db_exists())
        else:
            self.assertEqual([], self.dbm.get_table_names())

    def test_get_column_names(self):
        """Get column names for the default database."""
        for table in default_schema:
            column_names = [col.name for col in table.columns]
            self.assertEqual(column_names,
                             self.dbm.get_column_names(table.name))

    def test_get_default_database_version(self):
        """Get database version for the default entry named
        `database_version`.
        """
        self.assertEqual(default_db_version, self.dbm.get_database_version())

    def test_get_table_names(self):
        """Get table names for the default database."""
        self.assertEqual(sorted(table.name for table in default_schema),
                         sorted(self.dbm.get_table_names()))

    def test_has_table(self):
        self.assertIs(True, self.dbm.has_table('system'))
        self.assertIs(True, self.dbm.has_table('wiki'))
        self.assertIs(False, self.dbm.has_table('trac'))
        self.assertIs(False, self.dbm.has_table('blah.blah'))

    def test_no_database_version(self):
        """False is returned when entry doesn't exist"""
        self.assertFalse(self.dbm.get_database_version('trac_plugin_version'))

    def test_set_default_database_version(self):
        """Set database version for the default entry named
        `database_version`.
        """
        new_db_version = default_db_version + 1
        self.dbm.set_database_version(new_db_version)
        self.assertEqual(new_db_version, self.dbm.get_database_version())
        self.assertEqual([('INFO', 'Upgraded database_version from 45 to 46')],
                         self.env.log_messages)

        # Restore the previous version to avoid destroying the database
        # on teardown
        self.dbm.set_database_version(default_db_version)
        self.assertEqual(default_db_version, self.dbm.get_database_version())

    def test_set_get_plugin_database_version(self):
        """Get and set database version for an entry with an
        arbitrary name.
        """
        name = 'trac_plugin_version'
        db_ver = 1

        self.dbm.set_database_version(db_ver, name)
        self.assertEqual([], self.env.log_messages)
        self.assertEqual(db_ver, self.dbm.get_database_version(name))
        # DB update will be skipped when new value equals database version
        self.dbm.set_database_version(db_ver, name)
        self.assertEqual([], self.env.log_messages)

    def test_get_sequence_names(self):
        sequence_names = []
        if self.dbm.connection_uri.startswith('postgres'):
            for table in default_schema:
                for column in table.columns:
                    if column.name == 'id' and column.auto_increment:
                        sequence_names.append(table.name)
            sequence_names.sort()

        self.assertEqual(sequence_names, self.dbm.get_sequence_names())


class ModifyTableTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.dbm = DatabaseManager(self.env)
        self.schema = [
            Table('table1', key='col1')[
                Column('col1', auto_increment=True),
                Column('col2'),
                Column('col3'),
            ],
            Table('table2', key='col1')[
                Column('col1'),
                Column('col2'),
            ],
            Table('table3', key='col2')[
                Column('col1'),
                Column('col2', type='int'),
                Column('col3')
            ]
        ]
        self.dbm.create_tables(self.schema)
        self.new_schema = copy.deepcopy([self.schema[0], self.schema[2]])
        self.new_schema[0].remove_columns(('col2',))
        self.new_schema[1].columns.append(Column('col4'))
        self.new_schema.append(
            Table('table4')[
                Column('col1'),
            ]
        )

    def tearDown(self):
        self.dbm.drop_tables(['table1', 'table2', 'table3', 'table4'])
        self.env.reset_db()

    def _insert_data(self):
        table_data = [
            ('table1', ('col2', 'col3'),
             (('data1', 'data2'),
              ('data3', 'data4'))),
            ('table2', ('col1', 'col2'),
             (('data5', 'data6'),
              ('data7', 'data8'))),
            ('table3', ('col1', 'col2', 'col3'),
             (('data9', 10, 'data11'),
              ('data12', 13, 'data14'))),
        ]
        self.dbm.insert_into_tables(table_data)

    def test_drop_columns(self):
        """Data is preserved when column is dropped."""
        self._insert_data()

        self.dbm.drop_columns('table1', ('col2',))

        self.assertEqual(['col1', 'col3'], self.dbm.get_column_names('table1'))
        data = list(self.env.db_query("SELECT * FROM table1"))
        self.assertEqual((1, 'data2'), data[0])
        self.assertEqual((2, 'data4'), data[1])

    def test_drop_columns_multiple_columns(self):
        """Data is preserved when columns are dropped."""
        self._insert_data()

        self.dbm.drop_columns('table3', ('col1', 'col3'))

        self.assertEqual(['col2'], self.dbm.get_column_names('table3'))
        data = list(self.env.db_query("SELECT * FROM table3"))
        self.assertEqual((10,), data[0])
        self.assertEqual((13,), data[1])

    def test_drop_columns_non_existent_table(self):
        with self.assertRaises(self.env.db_exc.OperationalError) as cm:
            self.dbm.drop_columns('blah', ('col1',))
        self.assertIn(unicode(cm.exception), ('Table "blah" not found',
                                              'Table `blah` not found'))

    def test_upgrade_tables_have_new_schema(self):
        """The upgraded tables have the new schema."""
        self.dbm.upgrade_tables(self.new_schema)

        for table in self.new_schema:
            self.assertEqual([col.name for col in table.columns],
                             self.dbm.get_column_names(table.name))

    def test_upgrade_tables_data_is_migrated(self):
        """The data is migrated to the upgraded tables."""
        self._insert_data()

        self.dbm.upgrade_tables(self.new_schema)
        self.env.db_transaction("""
                INSERT INTO table1 (col3) VALUES ('data12')
                """)

        data = list(self.env.db_query("SELECT * FROM table1"))
        self.assertEqual((1, 'data2'), data[0])
        self.assertEqual((2, 'data4'), data[1])
        self.assertEqual(3, self.env.db_query("""
                SELECT col1 FROM table1 WHERE col3='data12'""")[0][0])
        data = list(self.env.db_query("SELECT * FROM table2"))
        self.assertEqual(('data5', 'data6'), data[0])
        self.assertEqual(('data7', 'data8'), data[1])
        data = list(self.env.db_query("SELECT * FROM table3"))
        self.assertEqual(('data9', 10, 'data11', None), data[0])
        self.assertEqual(('data12', 13, 'data14', None), data[1])

    def test_upgrade_tables_no_common_columns(self):
        schema = [
            Table('table1', key='id')[
                Column('id', auto_increment=True),
                Column('name'),
                Column('value'),
            ],
        ]
        self.dbm.upgrade_tables(schema)
        self.assertEqual(['id', 'name', 'value'],
                         self.dbm.get_column_names('table1'))
        self.assertEqual([], list(self.env.db_query("SELECT * FROM table1")))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ParseConnectionStringTestCase))
    suite.addTest(unittest.makeSuite(StringsTestCase))
    suite.addTest(unittest.makeSuite(ConnectionTestCase))
    suite.addTest(unittest.makeSuite(DatabaseManagerTestCase))
    suite.addTest(unittest.makeSuite(ModifyTableTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
