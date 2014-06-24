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
from ConfigParser import SafeConfigParser, NoSectionError, NoOptionError

from .exceptions import MygrateError


class MygrateConfigError(MygrateError):
    """Informational exception for bad MyGrate configuration."""
    pass


class MygrateConfig(object):

    def __init__(self, section='mygrate'):
        self.section = section
        self.parser = SafeConfigParser()
        self.parser.optionxform = str

        fnames = self._get_paths()
        if not self.parser.read(fnames):
            raise MygrateConfigError('No valid config files in '+repr(fnames))

    def _get_paths(self):
        env_config = os.getenv('MYGRATE_CONFIG', None)
        if env_config:
            return [os.path.expanduser(env_config)]
        else:
            home_config = os.path.expanduser('~/.mygrate.conf')
            global_config = '/etc/mygrate.conf'
            return [home_config, global_config]

    def call_entry_point(self, callbacks):
        try:
            entry_point = self.parser.get(self.section, 'entry_point')
        except (NoSectionError, NoOptionError):
            msg = 'Please specify entry_point in configuration'
            raise MygrateConfigError(msg)
        mod_name, attr_name = entry_point.rsplit(':', 1)
        mod = __import__(mod_name)
        func = getattr(mod, attr_name)
        func(callbacks, self)

    def get_mysql_connection_info(self, section=None):
        section = section or self.section
        ret = {}
        mapping = {'host': 'host',
                   'port': 'port',
                   'user': 'user',
                   'passwd': 'password',
                   'db': 'database',
                   'unix_socket': 'unix_socket'}
        for key, value in mapping.items():
            try:
                ret[key] = self.parser.get(section, value)
            except (NoSectionError, NoOptionError):
                pass
        return ret

    def get_mysql_binlog_info(self):
        try:
            index_file = self.parser.get(self.section, 'index_file')
        except (NoSectionError, NoOptionError):
            index_file = '/var/lib/mysql/mysql-bin.index'
        if not os.path.exists(index_file):
            raise MygrateConfigError('Invalid binlog index file: '+index_file)
        try:
            delay = self.parser.getfloat(self.section, 'tracking_delay')
        except (NoSectionError, NoOptionError):
            delay = 1.0
        return index_file, float(delay)

    def get_tracking_dir(self):
        try:
            tracking_dir = self.parser.get(self.section, 'tracking_dir')
        except (NoSectionError, NoOptionError):
            tracking_dir = os.path.expanduser('~/.binlog-tracking')
            try:
                os.makedirs(tracking_dir)
            except OSError:
                pass
        tracking_dir = os.path.expanduser(tracking_dir)
        if not os.path.isdir(tracking_dir):
            msg = 'Tracking directory does not exist: '+tracking_dir
            raise MygrateConfigError(msg)
        return tracking_dir


cfg = MygrateConfig()


# vim:et:fdm=marker:sts=4:sw=4:ts=4
