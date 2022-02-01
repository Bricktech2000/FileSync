from doctest import OutputChecker
import os
from re import T
from threading import local
import pysftp
import tempfile
import shutil

LOCKFILE = '.sync.lock'

def path_split(path):
  return path.split('/')


class LocalFileSystem:
  def __init__(self, config):
    self._config = config
    self.path = config.get('path')
    del self._config['path']

  def __del__(self):
    pass

  def read_file(self, path):
    abs_path = os.path.join(self.path, path)
    with open(abs_path, 'r') as f:
      return f.read()

  def write_file(self, path, data):
    abs_path = os.path.join(self.path, path)
    with open(abs_path, 'w') as f:
      f.write(data)

  def remove(self, path):
    abs_path = os.path.join(self.path, path)
    # os remove directory recursive python
    if os.path.isfile(abs_path) or os.path.islink(abs_path):
      os.remove(abs_path)
    if os.path.isdir(abs_path):
      shutil.rmtree(abs_path)

  # local_path must be absolute and path must be relative
  def from_local_path(self, local_path, path):
    if local_path is None: return
    abs_path = os.path.join(self.path, path)

    # https://stackoverflow.com/questions/123198/how-to-copy-files
    # https://www.geeksforgeeks.org/python-shutil-copytree-method/
    # https://stackoverflow.com/questions/2793789/create-destination-path-for-shutil-copy-files

    if os.path.isfile(local_path) or os.path.islink(local_path):
      os.makedirs(os.path.dirname(abs_path), exist_ok=True)
      shutil.copy(local_path, abs_path)
    if os.path.isdir(local_path):
      os.makedirs(os.path.dirname(abs_path), exist_ok=True)
      shutil.copytree(local_path, abs_path)

  # local_path will be absolute and path must be relative
  def to_local_path(self, path):
    out_path = os.path.join(self.path, path)
    out_path = out_path if os.path.isdir(path) or os.path.isfile(path) else None

    if out_path is None:
      print(f'DEBUG: file likely desynced with sync file: {path}')

    return out_path

  def lock(self):
    abs_path = os.path.join(self.path, LOCKFILE)
    with open(abs_path, 'w') as f: pass

  def unlock(self):
    abs_path = os.path.join(self.path, LOCKFILE)
    os.remove(abs_path)



class SSHFileSystem:
  def __init__(self, config):
    self.path = config['path']
    self._host = config['host']
    del config['path']
    del config['host']
    self._config = config

    self.connection = pysftp.Connection(self._host, **self._config)
    self.connection.chdir(self.path)

  def __del__(self):
    self.connection.close()

  def read_file(self, path):
    temp_file = os.path.join(tempfile.gettempdir(), path)
    self.connection.get(path, temp_file)

    with open(temp_file, 'r') as f:
      return f.read()

  def write_file(self, path, data):
    temp_file = os.path.join(tempfile.gettempdir(), path)
    abs_path = os.path.join(self.path, path)

    with open(temp_file, 'w') as f:
      f.write(data)

    self.connection.put(temp_file, abs_path)
  
  def remove(self, path):
    abs_path = os.path.join(self.path, path)

    if self.connection.isfile(path):
      self.connection.remove(path)
    if self.connection.isdir(path):
      # https://stackoverflow.com/questions/44151259/is-it-possible-to-remove-directory-with-some-contents-using-pysftp-module
      # hacky solution...
      self.connection.execute('rm -rf ' + abs_path.replace(' ', '\\ '))
      # sftp.rmdir(remote)

  # local_path must be absolute and path must be relative
  def from_local_path(self, local_path, path):
    if local_path is None: return
    abs_path = os.path.join(self.path, path)

    if os.path.isfile(local_path) or os.path.islink(local_path):
      try:
        self.connection.put(local_path, abs_path)
      except (FileNotFoundError, PermissionError):
        print(f'DEBUG: index desynced or permission error: {path}')
    if os.path.isdir(local_path):
      try:
        self.connection.mkdir(abs_path)
      except IOError:
        pass
      self.connection.put_r(local_path, abs_path)

  # local_path will be absolute and path must be relative
  def to_local_path(self, path):
    tempdir = tempfile.gettempdir()
    out_path = None

    if self.connection.isfile(path):
      out_path = os.path.join(tempdir, path)
      os.makedirs(os.path.dirname(out_path), exist_ok=True)
      self.connection.get(path, out_path)
    if self.connection.isdir(path):
      out_path = os.path.join(tempdir, *path_split(path)[:-1])
      os.makedirs(os.path.dirname(out_path), exist_ok=True)
      self.connection.get_r(path, out_path)

    if out_path is None:
      print(f'DEBUG: file likely desynced with sync file: {path}')

    return out_path
  
  def lock(self):
    temp_file = os.path.join(tempfile.gettempdir(), LOCKFILE)
    with open(temp_file, 'w') as f: pass
    self.connection.put(temp_file, LOCKFILE)

  def unlock(self):
    self.connection.remove(LOCKFILE)
