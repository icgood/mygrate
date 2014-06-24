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


class MygrateCallbacks(object):
    """Manages registration of callbacks for actions against tables.

    """

    def __init__(self):
        self.callbacks = {}

    def get_registered_tables(self):
        return self.callbacks.keys()

    def register(self, table, action, callback):
        """Registers a callback for a single action on a given table.

        :param table: The table the callback should apply to.
        :param action: The action the callback should apply to.
        :param callback: The function to call when the action happens on the
                         table.

        """
        self.callbacks.setdefault(table, {})
        self.callbacks[table][action] = callback

    def execute(self, table, action, *args, **kwargs):
        if table not in self.callbacks:
            return
        if action not in self.callbacks[table]:
            return
        callback = self.callbacks[table][action]
        callback(table, *args, **kwargs)


# vim:et:fdm=marker:sts=4:sw=4:ts=4
