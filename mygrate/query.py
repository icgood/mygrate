# Copyright (c) 2013 Ian C. Good
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#


import os
import os.path
import sys
import optparse
import cPickle
import MySQLdb
import MySQLdb.cursors


class InitialQuery(object):
    """Manages direct queries to MySQL for importing, validation, and
    re-validation.

    """

    def __init__(self, mysql_info, callbacks, action='INSERT'):
        self.mysql_info = mysql_info
        self.callbacks = callbacks
        self.action = action

    def run_callback(self, table, cols):
        """Executes the INSERT callback for the given table.

        :param table: The table being imported from.
        :param cols: The column dict containing the row data.

        """
        self.callbacks.execute(table, self.action, cols)

    def get_connection(self, db, streaming=True):
        """Creates and returns a connection to the MySQL server and selects the
        given database.

        :param db: The database name to select after connection.
        :param streaming: Whether or not a streaming MySQL cursor should be
                          used, for large data sets.
        :returns: A MySQL connection object.

        """
        kwargs = self.mysql_info.copy()
        kwargs['db'] = db
        kwargs['charset'] = 'utf8'
        if streaming:
            kwargs['cursorclass'] = MySQLdb.cursors.SSDictCursor
        else:
            kwargs['cursorclass'] = MySQLdb.cursors.DictCursor
        conn = MySQLdb.connect(**kwargs)
        return conn

    def process_table(self, full_table):
        """Does a streaming, full-table SELECT on the requested table to
        retrieve every row. Rows are then passed to `run_callback()`.

        :param full_table: The database and table names, separated by a period,
                           as given on the command line.

        """
        db, table = full_table.split('.')
        conn = self.get_connection(db)
        cur = conn.cursor()
        try:
            sql = 'SELECT * FROM `{0}`'.format(table)
            cur.execute(sql)
            while True:
                rows = cur.fetchmany(1000)
                if not rows:
                    break
                for row in rows:
                    self.run_callback(full_table, row)
        finally:
            cur.close()
            conn.close()


def main():
    from .config import cfg

    description = """\
This program attempts to import an entire table by creating job tasks for each
row.

Configuration for %prog is done with configuration files. This is either
/etc/mygrate.conf, ~/.mygrate.conf, or an alternative specified by the
MYGRATE_CONFIG environment variable.
"""
    usage = 'usage: %prog [options] <database>.<table> ...'
    op = optparse.OptionParser(usage=usage, description=description)
    options, requested_tables = op.parse_args()
    if not requested_tables:
        op.error('Must supply at least one database and table.')

    mysql_info = cfg.get_mysql_connection_info()
    callbacks = cfg.get_callbacks()

    query = InitialQuery(mysql_info, callbacks)
    for table in requested_tables:
        query.process_table(table)


if __name__ == '__main__':
    main()


# vim:et:fdm=marker:sts=4:sw=4:ts=4
