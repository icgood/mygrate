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
        """Returns a list of tables for which callbacks have been registered.

        """
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

    def register_module(self, table, module):
        """Registers a module containing all the action callbacks for a table.

        :param table: The table the callbacks should apply to.
        :param module: A module (or other object) containing "INSERT",
                       "UPDATE", or "DELETE" attributes that correspond to the
                       callbacks that should be executed.

        """
        self.callbacks.setdefault(table, {})
        if hasattr(module, 'INSERT'):
            self.callbacks[table]['INSERT'] = module.INSERT
        if hasattr(module, 'UPDATE'):
            self.callbacks[table]['UPDATE'] = module.UPDATE
        if hasattr(module, 'DELETE'):
            self.callbacks[table]['DELETE'] = module.DELETE

    def execute(self, table, action, *args, **kwargs):
        """Executes the callback registered to the given table and action. If
        no callback has been registered, nothing is executed.

        :param table: The table to execute the callback for. This table is
                      passed in as the first positional argument to the
                      callback.
        :param action: The action to execute the callback for.
        :param args: The positional arguments to pass in to the callback.
        :param kwargs: The keyword arguments to pass in to the callback.

        """
        if table not in self.callbacks:
            return
        if action not in self.callbacks[table]:
            return
        callback = self.callbacks[table][action]
        callback(table, *args, **kwargs)


# vim:et:fdm=marker:sts=4:sw=4:ts=4
