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
import cPickle
from celery import Celery, Task

from .config import cfg


broker_url = cfg.get_celery_info()
celery = Celery('mygrate.tasks', broker=broker_url)

errors_log = cfg.get_errors_log_file()
max_retries, retry_delay = cfg.get_retry_settings()

callbacks = cfg.get_callbacks()


class LoggedTask(Task):

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        err_info = {'action': self.__name__,
                    'args': args,
                    'kwargs': kwargs,
                    'exception': {'message': str(exc),
                                  'traceback': einfo.traceback}}
        err_raw = cPickle.dumps(err_info, cPickle.HIGHEST_PROTOCOL)
        with open(errors_log, 'a') as f:
            f.write(err_raw)
            f.flush()
            os.fsync(f.fileno())


task_settings = {'base': LoggedTask,
                 'max_retries': max_retries,
                 'retry_delay': retry_delay,
                 'ignore_result': True}


@celery.task(**task_settings)
def INSERT(table, cols):
    callbacks[table].INSERT(cols)


@celery.task(**task_settings)
def UPDATE(table, from_cols, to_cols):
    callbacks[table].UPDATE(from_cols, to_cols)


@celery.task(**task_settings)
def DELETE(table, cols):
    callbacks[table].DELETE(cols)


# vim:et:fdm=marker:sts=4:sw=4:ts=4
