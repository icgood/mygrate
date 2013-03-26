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

    def __init__(self):
        self.parser = SafeConfigParser()

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

    def get_celery_info(self):
        try:
            broker_url = self.parser.get('celery', 'broker_url')
        except (NoSectionError, NoOptionError):
            raise MygrateConfigError('Please specify the celery::broker_url configuration option.')
        return broker_url

    def get_callbacks(self):
        try:
            callbacks = self.parser.options('callbacks')
        except (NoSectionError):
            raise MygrateConfigError('Configuration section `callbacks` required.')
        ret = {}
        for opt_name in callbacks:
            mod = self.parser.get('callbacks', opt_name)
            ret[opt_name] = __import__(mod)
        return ret

    def get_mysql_connection_info(self):
        ret = {}
        mapping = {'host': 'host',
                   'port': 'port',
                   'user': 'user',
                   'passwd': 'password',
                   'unix_socket': 'unix_socket'}
        for key, value in mapping.items():
            try:
                ret[key] = self.parser.get('mysql', value)
            except (NoSectionError, NoOptionError):
                pass
        return ret

    def get_mysql_binlog_info(self):
        try:
            index_file = self.parser.get('mysql', 'binlog_index')
        except (NoSectionError, NoOptionError):
            index_file = '/var/log/mysql/mysql-bin.index'
        if not os.path.exists(index_file):
            raise MygrateConfigError('Invalid binlog index file: '+index_file)
        try:
            delay = self.parser.get('binlog', 'tracking_delay')
        except (NoSectionError, NoOptionError):
            delay = '1.0'
        return index_file, float(delay)

    def get_tracking_dir(self):
        try:
            tracking_dir = self.parser.get('binlog', 'tracking_dir')
        except (NoSectionError, NoOptionError):
            tracking_dir = os.path.expanduser('~/.binlog-tracking')
            try:
                os.makedirs(tracking_dir)
            except OSError:
                pass
        tracking_dir = os.path.expanduser(tracking_dir)
        if not os.path.isdir(tracking_dir):
            raise MygrateConfigError('Tracking directory does not exist: '+tracking_dir)
        return tracking_dir

    def get_errors_log_file(self):
        try:
            errors_log = self.parser.get('celery', 'errors_log')
        except (NoSectionError, NoOptionError):
            errors_log = '/dev/null'
        return errors_log

    def get_retry_settings(self):
        try:
            max_retries = int(self.parser.get('celery', 'max_retries'))
        except (NoSectionError, NoOptionError):
            max_retries = 3
        try:
            retry_delay = int(self.parser.get('celery', 'retry_delay'))
        except (NoSectionError, NoOptionError):
            retry_delay = 180
        return max_retries, retry_delay


cfg = MygrateConfig()


# vim:et:fdm=marker:sts=4:sw=4:ts=4
