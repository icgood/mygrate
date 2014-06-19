
import os
import os.path
import tempfile
import shutil
import subprocess
from datetime import datetime

from mox import MoxTestBase, IsA

from mygrate.binlog import (QueryBase, InsertQuery, UpdateQuery,
                            DeleteQuery, QueryParser, BinlogParser)


class TestQueryParsing(MoxTestBase):

    def test_insertquery_parse_initial_line(self):
        q = InsertQuery('INSERT INTO `testdb`.`testtable`', None, None, None)
        self.assertEqual('testdb.testtable', q.table)

    def test_updatequery_parse_initial_line(self):
        q = UpdateQuery('UPDATE `testdb`.`testtable`', None, None, None)
        self.assertEqual('testdb.testtable', q.table)

    def test_deletequery_parse_initial_line(self):
        q = DeleteQuery('DELETE FROM `testdb`.`testtable`', None, None, None)
        self.assertEqual('testdb.testtable', q.table)

    def test_querybase_parse_value(self):
        q = InsertQuery('INSERT INTO `testdb`.`testtable`', None, None, {})
        self.assertEqual('as\'df', q._parse_value("'as'df'", None))
        self.assertEqual('as\\x00df', q._parse_value("'as\\x00df'", None))
        self.assertEqual(9, q._parse_value('9', None))
        self.assertEqual(None, q._parse_value('NULL', None))
        self.assertEqual(datetime(2013, 1, 1, 13, 30), q._parse_value('2013-01-01 13:30:00', None))
        self.assertEqual(65531, q._parse_value('-5 (65531)', None))
        self.assertEqual('test', q._parse_value("b'01110100011001010111001101110100'", None))
        self.assertEqual(None, q._parse_value('invalid', None))

    def test_querybase_parse_value_encoding(self):
        q = InsertQuery('INSERT INTO `testdb`.`testtable`', None, None, {})
        self.assertEqual(u'asdf', q._parse_value("'asdf'", 'latin1'))
        self.assertEqual('10\xc3\xb72=Five', q._parse_value("'10\xf72=Five'", 'latin1').encode('utf8'))

    def test_querybase_parse(self):
        q = UpdateQuery('UPDATE `testdb`.`testtable`', None, None, {})
        q.parse("SET")
        q.parse("  @1='asdf'")
        q.parse("  @2=9")
        q.parse("WHERE")
        q.parse("  @1='jkl'")
        q.parse("  @2=10")
        self.assertEqual(['asdf', 9], q.values['SET'])
        self.assertEqual(['jkl', 10], q.values['WHERE'])

    def test_insertquery_finish(self):
        callbacks = self.mox.CreateMockAnything()
        callbacks.execute('testdb.testtable', 'INSERT', {'one': 'asdf', 'two': None})
        self.mox.ReplayAll()
        q = InsertQuery('INSERT INTO `testdb`.`testtable`', callbacks, {'testdb.testtable': ['one', 'two']}, {})
        q.parse("SET")
        q.parse("  @1='asdf'")
        q.parse("  @2=NULL")
        q.finish()

    def test_updatequery_finish(self):
        callbacks = self.mox.CreateMockAnything()
        callbacks.execute('testdb.testtable', 'UPDATE', {'one': 'jkl', 'two': None}, {'one': 'asdf', 'two': None})
        self.mox.ReplayAll()
        q = UpdateQuery('UPDATE `testdb`.`testtable`', callbacks, {'testdb.testtable': ['one', 'two']}, {})
        q.parse("SET")
        q.parse("  @1='asdf'")
        q.parse("  @2=NULL")
        q.parse("WHERE")
        q.parse("  @1='jkl'")
        q.parse("  @2=NULL")
        q.finish()

    def test_deletequery_finish(self):
        callbacks = self.mox.CreateMockAnything()
        callbacks.execute('testdb.testtable', 'DELETE', {'one': 'asdf', 'two': None})
        self.mox.ReplayAll()
        q = DeleteQuery('DELETE FROM `testdb`.`testtable`', callbacks, {'testdb.testtable': ['one', 'two']}, {})
        q.parse("WHERE")
        q.parse("  @1='asdf'")
        q.parse("  @2=NULL")
        q.finish()

    def test_queryparser(self):
        callbacks = self.mox.CreateMockAnything()
        callbacks.get_registered_tables().MultipleTimes().AndReturn(['testdb.testtable'])
        callbacks.execute('testdb.testtable', 'INSERT', {'one': 'asdf', 'two': None})
        callbacks.get_registered_tables().MultipleTimes().AndReturn(['testdb.testtable'])
        callbacks.execute('testdb.testtable', 'UPDATE', {'one': 'jkl', 'two': None}, {'one': 'asdf', 'two': None})
        callbacks.get_registered_tables().MultipleTimes().AndReturn(['testdb.testtable'])
        callbacks.execute('testdb.testtable', 'DELETE', {'one': 'asdf', 'two': None})
        self.mox.ReplayAll()
        qp = QueryParser(callbacks, {'testdb.testtable': ['one', 'two']}, {})
        qp.parse("INSERT INTO `testdb`.`testtable`")
        qp.parse("SET")
        qp.parse("  @1='asdf'")
        qp.parse("  @2=NULL")
        qp.parse("UPDATE `testdb`.`testtable`")
        qp.parse("SET")
        qp.parse("  @1='asdf'")
        qp.parse("  @2=NULL")
        qp.parse("WHERE")
        qp.parse("  @1='jkl'")
        qp.parse("  @2=NULL")
        qp.parse("DELETE FROM `testdb`.`testtable`")
        qp.parse("WHERE")
        qp.parse("  @1='asdf'")
        qp.parse("  @2=NULL")
        qp.finish()
        self.assertEqual(None, qp.current)


class TestBinlogParser(MoxTestBase):

    def setUp(self):
        super(TestBinlogParser, self).setUp()
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        super(TestBinlogParser, self).tearDown()
        shutil.rmtree(self.tmp_dir)

    def test_read_position(self):
        blp = BinlogParser(None, None, None, None)
        self.assertEqual('0', blp.read_position('file does not exist'))
        with tempfile.NamedTemporaryFile() as f:
            f.write('1234')
            f.flush()
            os.fsync(f.fileno())
            self.assertEqual('1234', blp.read_position(f.name))

    def test_write_position(self):
        blp = BinlogParser(None, None, None, None)
        with tempfile.NamedTemporaryFile() as f:
            self.assertEqual('0', blp.read_position(f.name))
            blp.write_position(f, '4321')
            self.assertEqual('4321', blp.read_position(f.name))
            blp.write_position(f, '1337')
            self.assertEqual('1337', blp.read_position(f.name))

    def test_read_index(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write('/path/to/file.1\n/path/to/file.2\n/path/to/file.3\n')
            f.flush()
            os.fsync(f.fileno())
            blp = BinlogParser(f.name, None, None, None)
            expected_binlogs = ['/path/to/file.1',
                                '/path/to/file.2',
                                '/path/to/file.3']
            self.assertEqual(expected_binlogs, blp.read_index())

    def test_build_pos_file(self):
        blp = BinlogParser(None, '/path/to/posdir', None, None)
        self.assertEqual('/path/to/posdir/binlogpos.000005', blp.build_pos_file('/path/to/mysql-binlog.000005'))
        self.assertEqual('/path/to/posdir/binlogpos.000001', blp.build_pos_file('/test/test.000001'))

    def test_process_binlog(self):
        pos_file = os.path.join(self.tmp_dir, 'binlogpos.000001')
        with open(pos_file, 'w') as f:
            f.write('1234')
        self.mox.StubOutWithMock(subprocess, 'Popen')
        proc = self.mox.CreateMockAnything()
        proc.stdin = self.mox.CreateMockAnything()
        proc.stdout = ['### INSERT INTO `testdb`.`testtable`\n',
                       '### SET\n',
                       "###   @1='asdf'\n",
                       "###   @2=NULL\n",
                       "# at 4321\n"]
        subprocess.Popen(['mysqlbinlog', '-v', '--base64-output=DECODE-ROWS', '/path/to/binlog.000001', '-j', '1234', '--set-charset=utf8'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE).AndReturn(proc)
        proc.stdin.close()
        callbacks = self.mox.CreateMockAnything()
        callbacks.get_registered_tables().MultipleTimes().AndReturn(['testdb.testtable'])
        callbacks.execute('testdb.testtable', 'INSERT', {'one': 'asdf', 'two': None})
        proc.wait()
        self.mox.ReplayAll()
        blp = BinlogParser(None, self.tmp_dir, callbacks, {'testdb.testtable': ['one', 'two']})
        blp.process_binlog('/path/to/binlog.000001')
        self.assertEqual('4321', blp.read_position(pos_file))

    def test_process_all_binlogs(self):
        blp = BinlogParser(None, None, None, None)
        self.mox.StubOutWithMock(blp, 'read_index')
        self.mox.StubOutWithMock(blp, 'process_binlog')
        self.mox.StubOutWithMock(os.path, 'getmtime')
        blp.read_index().AndReturn(['/path/to/test.1', '/path/to/test.2'])
        os.path.getmtime('/path/to/test.1').AndReturn(10.0)
        blp.process_binlog('/path/to/test.1')
        os.path.getmtime('/path/to/test.2').AndReturn(20.0)
        blp.process_binlog('/path/to/test.2')
        self.mox.ReplayAll()
        blp.process_all_binlogs()

    def test_set_binlogpos_at_end(self):
        binlog_file = os.path.join(self.tmp_dir, 'binlog.001')
        blp = BinlogParser(None, self.tmp_dir, None, None)
        with open(binlog_file, 'w') as f:
            f.write('x'*256)
        blp.set_binlogpos_at_end(binlog_file)
        self.assertEqual('256', blp.read_position(os.path.join(self.tmp_dir, 'binlogpos.001')))


# vim:et:fdm=marker:sts=4:sw=4:ts=4
