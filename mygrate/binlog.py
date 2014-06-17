
import os
import sys
import os.path
import re
import signal
import subprocess
import optparse
import traceback
import glob
from ast import literal_eval
from time import sleep

import MySQLdb

from . import tasks
from .config import cfg


class QueryBase(object):
    """The base class for keeping track of a single query loaded in from the
    command:

        mysqlbinlog -v --base64-output=DECODE-ROWS /path/to/binlog.00000x

    The binlog must be in ROW format. This format is easier for a machine to
    process.

    """

    _column_pattern = re.compile(r'^  @(\d+)=(.*)$')
    _int_pattern = re.compile(r'\(([^\)]*)\)')

    def __init__(self, line, callbacks, column_names, char_sets):
        self.callbacks = callbacks
        self.column_names = column_names
        self.char_sets = char_sets
        self.table = None
        self.invalid = False
        self.current_value_type = None
        self.values = {'WHERE': [], 'SET': []}
        self._parse_initial_line(line)

    def _parse_initial_line(self, line):
        match = self._initial_pattern.match(line)
        if not match:
            self.invalid = True
            return
        identifiers = [ident.strip('`') for ident in match.group(1).split('.')]
        self.table = '.'.join(identifiers)

    def _parse_value(self, value, char_set):
        try:
            literal = literal_eval(value)
        except Exception:
            before_space, sep, after_space = value.partition(' ')
            if sep == ' ':
                return self._parse_value(before_space, char_set)
        else:
            if char_set and isinstance(literal, str):
                return literal.decode(char_set)
            else:
                return literal
        return None

    def parse(self, line):
        """Adds the contents of the given line to the current query. The
        mysqlbinlog command uses two basic sections `SET` and `WHERE` to define
        the different parts of the queries.

        :param line: The line to parse into the query.

        """
        if line == 'SET' or line == 'WHERE':
            self.current_value_type = line
            return
        match = self._column_pattern.match(line)
        if not match:
            self.invalid = True
            return
        char_set = self.char_sets.get(self.table)
        col_value = self._parse_value(match.group(2), char_set)
        self.values[self.current_value_type].append(col_value)

    def __repr__(self):
        return '<Query {0} {1} WHERE={2!s} SET={3!s}>'.format(
            self.type,
            self.table,
            self.values['WHERE'],
            self.values['SET'])


class InsertQuery(QueryBase):
    _initial_pattern = re.compile(r'^INSERT INTO (.*)$')
    type = 'INSERT'

    def finish(self):
        """When the query is finished, its numeric column references are
        translated into column names using a lookup table, resulting in a dict
        object that is then passed to the callback.

        """
        table_column_names = self.column_names[self.table]
        set_vals = {}
        for i, val in enumerate(self.values['SET']):
            key = table_column_names[i]
            set_vals[key] = val
        callback = getattr(tasks, self.type)
        callback.delay(self.table, set_vals)


class UpdateQuery(QueryBase):
    _initial_pattern = re.compile(r'^UPDATE (.*)$')
    type = 'UPDATE'

    def finish(self):
        """When the query is finished, its numeric column references are
        translated into column names using a lookup table, resulting in a dict
        object that is then passed to the callback.

        """
        table_column_names = self.column_names[self.table]
        where_vals = {}
        for i, val in enumerate(self.values['WHERE']):
            key = table_column_names[i]
            where_vals[key] = val
        set_vals = {}
        for i, val in enumerate(self.values['SET']):
            key = table_column_names[i]
            set_vals[key] = val
        callback = getattr(tasks, self.type)
        callback.delay(self.table, where_vals, set_vals)


class DeleteQuery(QueryBase):
    _initial_pattern = re.compile(r'^DELETE FROM (.*)$')
    type = 'DELETE'

    def finish(self):
        """When the query is finished, its numeric column references are
        translated into column names using a lookup table, resulting in a dict
        object that is then passed to the callback.

        """
        table_column_names = self.column_names[self.table]
        where_vals = {}
        for i, val in enumerate(self.values['WHERE']):
            key = table_column_names[i]
            where_vals[key] = val
        callback = getattr(tasks, self.type)
        callback.delay(self.table, where_vals)


class QueryParser(object):
    """Keeps track of the current query being read from the binlog. If it sees a
    new query, it marks the previous query as finished and sends it to the
    callback.

    """

    def __init__(self, callbacks, column_names, char_sets):
        self.current = None
        self.callbacks = callbacks
        self.column_names = column_names
        self.char_sets = char_sets

    def parse(self, line):
        """Checks if the line is the beginning of a new query or should be added
        on to the current query.

        :param line: The line to process.

        """
        if line.startswith('INSERT'):
            self._handle_completion()
            query = InsertQuery(line, self.callbacks, self.column_names,
                                self.char_sets)
            self.current = query if query.table in self.callbacks else None
        elif line.startswith('UPDATE'):
            self._handle_completion()
            query = UpdateQuery(line, self.callbacks, self.column_names,
                                self.char_sets)
            self.current = query if query.table in self.callbacks else None
        elif line.startswith('DELETE'):
            self._handle_completion()
            query = DeleteQuery(line, self.callbacks, self.column_names,
                                self.char_sets)
            self.current = query if query.table in self.callbacks else None
        elif self.current:
            self.current.parse(line)

    def finish(self):
        """Called at the end of the binlog, so that the current query can be
        marked complete and sent to the callback.

        """
        self._handle_completion()
        self.current = None

    def _handle_completion(self):
        if self.current:
            self.current.finish()


class BinlogParser(object):

    def __init__(self, index_file, pos_dir, callbacks, column_names=None,
                 char_sets=None):
        self.done = False
        self.index_file = index_file
        self.pos_dir = pos_dir
        self.callbacks = callbacks
        self.column_names = column_names or {}
        self.char_sets = char_sets or {}
        self.binlog_mtimes = {}

    def _load_one_table_names(self, conn, db, table):
        cur = conn.cursor()
        try:
            cur.execute("""SELECT `COLUMN_NAME` FROM
                           `INFORMATION_SCHEMA`.`COLUMNS`
                           WHERE `TABLE_SCHEMA`=%s AND `TABLE_NAME`=%s""",
                        (db, table))
            return [row[0] for row in cur.fetchall()]
        finally:
            cur.close()

    def load_column_names(self, mysql_info):
        """Connects to the MySQL server and loads column names for all the
        tables for which there are callbacks.

        :param mysql_info: Contains the details about the MySQL connection.

        """
        kwargs = mysql_info.copy()
        conn = MySQLdb.connect(**kwargs)

        try:
            for full_table in self.callbacks.keys():
                db, table = full_table.split('.', 1)
                names = self._load_one_table_names(conn, db, table)
                self.column_names[full_table] = names
        finally:
            conn.close()

    def _load_one_table_charset(self, conn, db, table):
        cur = conn.cursor()
        try:
            cur.execute("""SELECT `CCSA`.`CHARACTER_SET_NAME` FROM
`INFORMATION_SCHEMA`.`TABLES` `T`,
`INFORMATION_SCHEMA`.`COLLATION_CHARACTER_SET_APPLICABILITY` `CCSA`
WHERE `CCSA`.`COLLATION_NAME` = `T`.`TABLE_COLLATION`
AND `T`.`TABLE_SCHEMA` = %s
AND `T`.`TABLE_NAME` = %s""", (db, table))
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            cur.close()

    def load_character_sets(self, mysql_info):
        """Connects to the MySQL server and loads table character sets for all
        the tables for which there are callbacks.

        :param mysql_info: Contains the details about the MySQL connection.

        """
        kwargs = mysql_info.copy()
        conn = MySQLdb.connect(**kwargs)

        try:
            for full_table in self.callbacks.keys():
                db, table = full_table.split('.', 1)
                charset = self._load_one_table_charset(conn, db, table)
                self.char_sets[full_table] = charset
        finally:
            conn.close()

    def read_position(self, pos_file):
        """Reads the latest binlog position from the position tracking file.

        :param pos_file: The path to the position tracking file.
        :returns: The position from the file, if it exists, or 0.

        """
        try:
            with open(pos_file, 'r') as f:
                ret = f.read().rstrip()
                if ret:
                    return ret
        except IOError, (err, s):
            if err != 2:
                raise
        return '0'

    def write_position(self, f, pos):
        """Writes the binlog position to the position tracking file, immediately
        flushing write caches to disk. The file is always truncated before
        being written to so that its contents are only the latest position.

        :param f: The file object to write to.
        :param pos: The position to write to f.

        """
        f.seek(0, os.SEEK_SET)
        f.truncate()
        f.write(pos)
        f.flush()

    def read_index(self):
        """Reads the known binlog file paths from the binlog index file, which
        is managed by MySQL.

        :returns: List of file paths to the binlogs.

        """
        index_dir = os.path.dirname(self.index_file)
        with open(self.index_file, 'r') as f:
            ret = []
            for line in f:
                binlog = line.rstrip()
                binlog = os.path.normpath(os.path.join(index_dir, binlog))
                ret.append(binlog)
            return ret

    def build_pos_file(self, binlog):
        """Given a binlog file path, build a corresponding position tracking
        file path based on the configured tracking directory.

        :param binlog: The binlog file path.
        :returns: The corresponding path to the tracking file.

        """
        binlog_base, binlog_ext = os.path.splitext(binlog)
        return os.path.join(self.pos_dir, 'binlogpos'+binlog_ext)

    def process_binlog(self, binlog):
        """Sweeps through a single binlog, checking it for updates after the
        last known position read from the tracking file. If new positions are
        seen, the tracking file is updated with the new position. Queries are
        processed on the spot and sent to the callback.

        :param binlog: The path to the binlog file.

        """
        p = QueryParser(self.callbacks, self.column_names, self.char_sets)

        pos_file = self.build_pos_file(binlog)

        last_position = self.read_position(pos_file)
        print 'processing', binlog, 'from', last_position
        writepos = open(pos_file, 'w')
        self.write_position(writepos, last_position)

        args = ['mysqlbinlog', '-v', '--base64-output=DECODE-ROWS', binlog,
                '-j', last_position,
                '--set-charset=utf8']

        proc = subprocess.Popen(args, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE)
        proc.stdin.close()

        try:
            for line in proc.stdout:
                if self.done:
                    break
                if line.startswith('### '):
                    p.parse(line[4:].rstrip('\r\n'))
                elif line.startswith('# at '):
                    last_position = line[5:].rstrip()
                    self.write_position(writepos, last_position)
            else:
                p.finish()
        except Exception:
            traceback.print_exc()
        finally:
            writepos.close()
            proc.wait()

    def process_all_binlogs(self):
        """Sweeps through all the binlogs in the index. The index is read every
        sweep in case MySQL is restarted or rotates to a new binlog file. This
        method also checks each binlogs mtime to see if it has been modified
        since the last sweep.

        """
        binlogs = self.read_index()
        for binlog in binlogs:
            if not self.done:
                old_mtime = self.binlog_mtimes.get(binlog, 0.0)
                self.binlog_mtimes[binlog] = float(os.path.getmtime(binlog))
                if old_mtime < self.binlog_mtimes[binlog]:
                    self.process_binlog(binlog)

    def set_binlogpos_at_end(self, binlog):
        """Manually sets the binlog's position tracking file to the end of the
        binlog, so that future sweeps will not act upon any existing entries.

        :param binlog: The file path to the binlog.

        """
        pos_file = self.build_pos_file(binlog)

        old_pos = self.read_position(pos_file)
        binlog_size = os.path.getsize(binlog)
        with open(pos_file, 'w') as f:
            self.write_position(f, str(binlog_size))
        print 'changing', pos_file, 'from', old_pos, 'to', binlog_size


def confirm_skip_existing():
    print 'This utility will seek the binlog tracking files to the end of all'
    print 'existing entries. All previous entries will be skipped. There is no'
    print 'easy way to undo this operation!'
    print
    while True:
        answer = raw_input('Are you sure?  N/y: ')
        if answer in ['y', 'Y']:
            return
        elif answer in ['n', 'N', '']:
            sys.exit(1)


def skip_existing():
    """This function is declared as the entry point for the
    `mygrate-skip` command.

    """
    description = """\
This program calculates the latest binlog positions and creates/modifies the
tracking files to those positions. Subsequent executions of the binlog parser
will start at these new positions.

Configuration for %prog is done with configuration files. This is either
/etc/mygrate.ini, ~/.mygrate.ini, or an alternative specified by the
MYGRATE_CONFIG environment variable.
"""
    op = optparse.OptionParser()
    op.add_option('-f', '--force', action='store_true', default=False,
                  help='Do not ask for confirmation, just do it.')
    options, extra = op.parse_args()

    if not options.force:
        confirm_skip_existing()

    binlog_index, tracking_delay = cfg.get_mysql_binlog_info()
    tracking_dir = cfg.get_tracking_dir()
    callbacks = cfg.get_callbacks()
    parser = BinlogParser(binlog_index, tracking_dir, callbacks)
    binlogs = parser.read_index()
    for binlog in binlogs:
        parser.set_binlogpos_at_end(binlog)


def main():
    """This function is declared the entry point for the
    `mygrate-binlog` command.

    """
    description = """\
This program follows changes in the MySQL binlog, producing job tasks for each
change. It is intended to be long-running, and will briefly pause after
catching up each binlog before checking for new changes.

Configuration for %prog is done with configuration files. This is either
/etc/mygrate.ini, ~/.mygrate.ini, or an alternative specified by the
MYGRATE_CONFIG environment variable.
"""
    op = optparse.OptionParser(description=description)
    op.parse_args()

    tracking_dir = cfg.get_tracking_dir()
    binlog_index, tracking_delay = cfg.get_mysql_binlog_info()
    callbacks = cfg.get_callbacks()
    parser = BinlogParser(binlog_index, tracking_dir, callbacks)

    def graceful_quit(sig, frame):
        parser.done = True

    signal.signal(signal.SIGINT, graceful_quit)
    signal.signal(signal.SIGTERM, graceful_quit)

    mysql_info = cfg.get_mysql_connection_info()
    parser.load_column_names(mysql_info)
    parser.load_character_sets(mysql_info)

    while not parser.done:
        parser.process_all_binlogs()
        if not parser.done:
            sleep(tracking_delay)


if __name__ == '__main__':
    main()


# vim:et:fdm=marker:sts=4:sw=4:ts=4
