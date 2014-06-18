
import os.path
import cPickle
import MySQLdb
import MySQLdb.cursors

from mox import MoxTestBase, IsA

from mygrate.query import InitialQuery


class TestInitialQuery(MoxTestBase):

    def test_run_callback(self):
        callbacks = self.mox.CreateMockAnything()
        callbacks.execute('test.test', 'TEST', {'one': 1, 'two': 2})
        self.mox.ReplayAll()
        importer = InitialQuery(None, callbacks, 'TEST')
        importer.run_callback('test.test', {'one': 1, 'two': 2})

    def test_get_connect(self):
        self.mox.StubOutWithMock(MySQLdb, 'connect')
        MySQLdb.connect(host='testhost', user='testuser', passwd='testpass',
                        db='testdb', charset='utf8', cursorclass=MySQLdb.cursors.SSDictCursor).AndReturn(13)
        options = {'host': 'testhost', 'user': 'testuser', 'passwd': 'testpass'}
        self.mox.ReplayAll()
        importer = InitialQuery(options, None, None)
        self.assertEqual(13, importer.get_connection('testdb'))

    def test_process_table(self):
        importer = InitialQuery(None, None, None)
        self.mox.StubOutWithMock(importer, 'get_connection')
        self.mox.StubOutWithMock(importer, 'run_callback')
        conn = self.mox.CreateMockAnything()
        importer.get_connection('testdb').AndReturn(conn)
        cur = self.mox.CreateMockAnything()
        conn.cursor().AndReturn(cur)
        cur.execute('SELECT * FROM `testtable`')
        cur.fetchmany(IsA(int)).AndReturn([{'one': 1, 'two': 2}, {'one': 3, 'two': 4}])
        importer.run_callback('testdb.testtable', {'one': 1, 'two': 2})
        importer.run_callback('testdb.testtable', {'one': 3, 'two': 4})
        cur.fetchmany(IsA(int)).AndReturn([])
        cur.close()
        conn.close()
        self.mox.ReplayAll()
        importer.process_table('testdb.testtable')


# vim:et:fdm=marker:sts=4:sw=4:ts=4
