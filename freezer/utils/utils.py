"""
(c) Copyright 2014,2015 Hewlett-Packard Development Company, L.P.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Freezer general utils functions
"""
import datetime
import errno
import logging
import os
import subprocess
import sys
import time

from distutils import spawn as distspawn
from functools import wraps
from oslo_config import cfg
from oslo_log import log
from six.moves import configparser


CONF = cfg.CONF
LOG = log.getLogger(__name__)


def create_dir_tree(dir):
    try:
        os.makedirs(dir)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(dir):
            pass
        else:
            raise exc


def is_empty_dir(path):
    return not os.listdir(path)


def create_dir(directory, do_log=True):
    """
    Creates a directory if it doesn't exists and write the execution
    in the logs
    """
    expanded_dir_name = os.path.expanduser(directory)
    try:
        if not os.path.isdir(expanded_dir_name):
            if do_log:
                logging.warning('[*] Directory {0} does not exists,\
                creating...'.format(expanded_dir_name))
            os.makedirs(expanded_dir_name)
        else:
            if do_log:
                logging.warning('[*] Directory {0} found!'.format(
                    expanded_dir_name))
    except Exception as error:
        err = '[*] Error while creating directory {0}: {1}\
            '.format(expanded_dir_name, error)
        raise Exception(err)


def save_config_to_file(config, f, section='freezer_default'):
    parser = configparser.ConfigParser()
    parser.add_section(section)
    for option, option_value in config.items():
        parser.set(section, option, option_value)
    parser.write(f)
    f.close()


class DateTime(object):
    def __init__(self, value):
        if isinstance(value, int):
            self.date_time = datetime.datetime.fromtimestamp(value)
        elif isinstance(value, datetime.datetime):
            self.date_time = value
        else:
            fmt = '%Y-%m-%dT%H:%M:%S'
            try:
                self.date_time = datetime.datetime.strptime(value, fmt)
            except Exception:
                raise Exception('bad datetime format: "{0}'.format(value))

    @property
    def timestamp(self):
        return int(time.mktime(self.date_time.timetuple()))

    def __repr__(self):
        return self.date_time.strftime('%Y-%m-%d %H:%M:%S')

    def __sub__(self, other):
        assert isinstance(other, DateTime)
        return self.date_time - other.date_time  # return timedelta

    @staticmethod
    def now():
        return DateTime(datetime.datetime.now())


def path_join(*args):
    """Should work for windows and linux"""
    return "/".join([str(x) for x in args])


def get_mount_from_path(path):
    """
    Take a file system path as argument and return the mount point
    for that file system path.

    :param path: file system path
    :returns: mount point of path, rest of the path
    """

    if not os.path.exists(path):
        logging.critical('[*] Error: provided path does not exist: {0}'
                         .format(path))
        raise IOError

    mount_point_path = os.path.abspath(path)

    while not os.path.ismount(mount_point_path):
        mount_point_path = os.path.dirname(mount_point_path)
    return mount_point_path, os.path.relpath(path, mount_point_path)


# see: http://goo.gl/kTQMs
HUMAN_2_SYMBOLS = {
    'customary': ('B', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y'),
    'customary_ext': ('byte', 'kilo', 'mega', 'giga', 'tera', 'peta', 'exa',
                      'zetta', 'iotta'),
    'iec': ('Bi', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi'),
    'iec_ext': ('byte', 'kibi', 'mebi', 'gibi', 'tebi', 'pebi', 'exbi',
                'zebi', 'yobi'),
}


def human2bytes(s):
    """
    Attempts to guess the string format based on default symbols
    set and return the corresponding bytes as an integer.
    When unable to recognize the format ValueError is raised.
    """
    if s.isdigit():
        return int(s)

    if s in (False, None, '-1'):
        return -1

    init = s
    num = ""
    while s and s[0:1].isdigit() or s[0:1] == '.':
        num += s[0]
        s = s[1:]
    num = float(num)
    letter = s.strip()
    for name, sset in HUMAN_2_SYMBOLS.items():
        if letter in sset:
            break
    else:
        if letter == 'k':
            # treat 'k' as an alias for 'K' as per: http://goo.gl/kTQMs
            sset = HUMAN_2_SYMBOLS['customary']
            letter = letter.upper()
        else:
            raise ValueError("can't interpret %r" % init)
    prefix = {sset[0]: 1}
    for i, s in enumerate(sset[1:]):
        prefix[s] = 1 << (i + 1) * 10
    return int(num * prefix[letter])


def create_subprocess(cmd):
    """
    Create a new subprocess in the OS
    :param cmd: command to execute in the subprocess
    :return: the output and errors of the subprocess
    """
    process = subprocess.Popen(cmd,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    return process.communicate()


def date_to_timestamp(date):
    fmt = '%Y-%m-%dT%H:%M:%S'
    opt_backup_date = datetime.datetime.strptime(date, fmt)
    return int(time.mktime(opt_backup_date.timetuple()))


class Bunch:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __getattr__(self, item):
        return self.__dict__.get(item)


class ReSizeStream:
    """
    Iterator/File-like object for changing size of chunk in stream
    """
    def __init__(self, stream, length, chunk_size):
        self.stream = stream
        self.length = length
        self.chunk_size = chunk_size
        self.reminder = ""
        self.transmitted = 0

    def __len__(self):
        return self.length

    def __iter__(self):
        return self

    def next(self):
        logging.info("Transmitted {0} of {1}".format(self.transmitted,
                                                     self.length))
        chunk_size = self.chunk_size
        if len(self.reminder) > chunk_size:
            result = self.reminder[:chunk_size]
            self.reminder = self.reminder[chunk_size:]
            self.transmitted += len(result)
            return result
        else:
            stop = False
            while not stop and len(self.reminder) < chunk_size:
                try:
                    self.reminder += next(self.stream)
                except StopIteration:
                    stop = True
            if stop:
                result = self.reminder
                if len(self.reminder) == 0:
                    raise StopIteration()
                self.reminder = []
                self.transmitted += len(result)
                return result
            else:
                result = self.reminder[:chunk_size]
                self.reminder = self.reminder[chunk_size:]
                self.transmitted += len(result)
                return result

    def read(self, chunk_size):
        self.chunk_size = chunk_size
        return self.next()


def dequote(s):
    """
    If a string has single or double quotes around it, remove them.
    Make sure the pair of quotes match.
    If a matching pair of quotes is not found, return the string unchanged.
    """
    s = s.rstrip('\n')
    if (s[0] == s[-1]) and s.startswith(("'", '"')):
        return s[1:-1]
    return s


def find_executable(name):
    return distspawn.find_executable(name)


def openssl_path():
    from freezer.utils import winutils
    if winutils.is_windows():
        return 'openssl'
    else:
        return find_executable('openssl')


def tar_path():
    """This function returns tar binary path"""
    from freezer.utils import winutils
    if winutils.is_windows():
        path_to_binaries = os.path.dirname(os.path.abspath(__file__))
        return '{0}\\bin\\tar.exe'.format(path_to_binaries)

    tar = (get_executable_path('gnutar') or get_executable_path('gtar')
           or get_executable_path('tar'))
    if not tar:
        raise Exception('Please install gnu tar (gtar) as it is a '
                        'mandatory requirement to use freezer.')
    return tar


def get_executable_path(binary):
    """
    This function returns the executable path of a given binary
    if it is found in the system.
    :param binary:
    :type binary: str
    :rtype: str
    :return: Absoulte Path to the executable file
    """
    from freezer.utils import winutils
    if winutils.is_windows():
        path_to_binaries = os.path.dirname(os.path.abspath(__file__))
        return '{0}\\bin\\{1}.exe'.format(path_to_binaries, binary)

    elif is_bsd():
        return (distspawn.find_executable(binary) or
                distspawn.find_executable(binary, path=':'.join(sys.path)))
    else:
        return distspawn.find_executable(binary)


def alter_proxy(proxy):
    """
    Read proxy option from dictionary and alter the HTTP_PROXY and/or
    HTTPS_PROXY system variables
    """
    # Default case where 'proxy' key is not set -- do nothing
    proxy_value = proxy.lower()
    # python-swift client takes into account both
    # upper and lower case proxies so clear them all
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("HTTPS_PROXY", None)
    if proxy_value.startswith('http://') or \
            proxy_value.startswith('https://'):
        logging.info('[*] Using proxy {0}'.format(proxy_value))
        os.environ['HTTP_PROXY'] = str(proxy_value)
        os.environ['HTTPS_PROXY'] = str(proxy_value)
    else:
        raise Exception('Proxy has unknown scheme')

def is_bsd():
    return 'darwin' in sys.platform or 'bsd' in sys.platform


def shield(func):
    """Remove try except boilerplate code from functions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            logging.error(error)
    return wrapper


def delete_file(path_to_file):
    """Delete a file from the file system
    """
    try:
        os.remove(path_to_file)
    except Exception:
        logging.warning("Error deleting file {0}".format(path_to_file))


class Namespace(dict):
    """A dict subclass that exposes its items as attributes.

    Warning: Namespace instances do not have direct access to the
    dict methods.

    """

    def __init__(self, obj={}):
        super(Namespace, self).__init__(obj)

    def __dir__(self):
        return tuple(self)

    def __repr__(self):
        return "%s(%s)" % (type(self).__name__,
                           super(Namespace, self).__repr__())

    def __getattribute__(self, name):
        try:
            return self[name]
        except KeyError:
            # Return None in case the value doesn't exists
            # this is not an issue for the apiclient because it skips
            # None values
            return None

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        del self[name]

    @classmethod
    def from_object(cls, obj, names=None):
        if names is None:
            names = dir(obj)
        ns = {name:getattr(obj, name) for name in names}
        return cls(ns)

    @classmethod
    def from_mapping(cls, ns, names=None):
        if names:
            ns = {name: ns[name] for name in names}
        return cls(ns)

    @classmethod
    def from_sequence(cls, seq, names=None):
        if names:
            seq = {name: val for name, val in seq if name in names}
        return cls(seq)

    @staticmethod
    def hasattr(ns, name):
        try:
            object.__getattribute__(ns, name)
        except AttributeError:
            return False
        return True

    @staticmethod
    def getattr(ns, name):
        return object.__getattribute__(ns, name)

    @staticmethod
    def setattr(ns, name, value):
        return object.__setattr__(ns, name, value)

    @staticmethod
    def delattr(ns, name):
        return object.__delattr__(ns, name)


def set_max_process_priority():
    """ Set freezer in max priority on the os """
    # children processes inherit niceness from father
    try:
        LOG.warning(
            '[*] Setting freezer execution with high CPU and I/O priority')
        PID = os.getpid()
        # Set cpu priority
        os.nice(-19)
        # Set I/O Priority to Real Time class with level 0
        subprocess.call([
            u'{0}'.format(find_executable("ionice")),
            u'-c', u'1', u'-n', u'0', u'-t',
            u'-p', u'{0}'.format(PID)
        ])
    except Exception as priority_error:
        LOG.warning('[*] Priority: {0}'.format(priority_error))
