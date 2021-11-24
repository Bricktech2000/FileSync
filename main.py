# python watchdog: https://www.geeksforgeeks.org/create-a-watchdog-in-python-to-look-for-filesystem-changes/
# python pysftp: https://appdividend.com/2020/06/08/python-sftp-how-to-access-sftp-server-using-pysftp/
# https://pysftp.readthedocs.io/en/release_0.2.8/pysftp.html
# https://stackoverflow.com/questions/38939454/verify-host-key-with-pysftp

import os
import sys
import time
import json
import pysftp
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


REMOTE = {
  'host': 'admin-bricktech2000.emilien.ca',
  'port': 55522,
  'username': 'server',
  'private_key': '~/.ssh/id_rsa'
}
LOCAL_CWD = os.getcwd()
REMOTE_CWD = '/home/server/Files/'
BUF_SIZE = 65536
UPLOAD_TO_REMOTE = True

SYNC_FILE = '.sync'
REMOTE_SYNC_FILE = '.sync.remote'
cnopts = pysftp.CnOpts()
cnopts.hostkeys = None   
REMOTE['cnopts'] = cnopts
SYNC_DATA = '.sync.data'
SYNC_TIME = '.sync.time'

def get_ms():
  return round(time.time() * 1000)

def path_split(path):
  return path.split('/')

def is_file(index):
  return isinstance(index[SYNC_DATA], str) and exists(index)
def is_directory(index):
  return SYNC_DATA is True and exists(index)
def exists(index):
  return index[SYNC_DATA] is not None
def has_data_changed(index1, index2):
  return index1[SYNC_DATA] != index2[SYNC_DATA] or is_directory(index1[SYNC_DATA]) or is_directory(index2[SYNC_DATA])


EMPTY_INDEX = {'.': {SYNC_TIME: get_ms()}}

def load_index(path):
  if not os.path.exists(path):
    with open(path, 'w') as f:
      f.write(json.dumps(EMPTY_INDEX))

  with open(path, 'r') as f:
    return json.loads(f.read())

def dump_index(index, path):
  with open(path, 'w') as f:
    f.write(json.dumps(index))

def get_file_hash(path):
  sha1 = hashlib.sha1()
  sha1.update(path.encode('utf-8'))
  if os.path.isdir(path):
    return True
  if not os.path.exists(path):
    return None
  with open(path, 'rb') as f:
    while True:
      data = f.read(BUF_SIZE)
      if not data: break
      sha1.update(data)
  return sha1.hexdigest()

def get_name_hash(path):
  sha1 = hashlib.sha1()
  sha1.update(path.encode('utf-8'))
  return sha1.hexdigest()

def update_index_recursive():
  # https://stackoverflow.com/questions/19587118/iterating-through-directories-with-python
  # https://stackoverflow.com/questions/7201203/python-current-directory-in-an-os-walk
  print('updating index recursively...')
  full_path = LOCAL_CWD + '/'
  for subdir, dirs, files in os.walk(full_path):
    for file in files:
      update_index(SYNC_FILE, os.path.join('.', subdir.replace(full_path, '', 1), file))
  print('done.')

def update_index(sync_file, path):
  path = path_split(path)
  if len(path) == 1 and path[0] == '.': return
  if len(path) > 1 and path[1] == '.git': return
  if SYNC_FILE in path: return
  if REMOTE_SYNC_FILE in path: return

  file_hash = get_file_hash(os.path.join(*path))
  filename = path[-1]
  subdirectories = path[:-1]

  index = load_index(sync_file)
  current_index = index
  for subdirectory in subdirectories:
    if subdirectory not in current_index: current_index[subdirectory] = {}
    current_index[subdirectory][SYNC_TIME] = get_ms()
    current_index[subdirectory][SYNC_DATA] = True
    current_index = current_index[subdirectory]

  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  if filename not in current_index: current_index[filename] = {}
  current_index[filename][SYNC_DATA] = file_hash
  current_index[filename][SYNC_TIME] = get_ms()

  dump_index(index, sync_file)

def sync_with_remote():
  print('syncing files with remote...')
  if not UPLOAD_TO_REMOTE: return

  with pysftp.Connection(**REMOTE) as sftp:
    sftp.chdir(REMOTE_CWD)
    try:
      sftp.get(SYNC_FILE, REMOTE_SYNC_FILE)
    except FileNotFoundError:
      print('warning: remote sync file not found. uploading empty sync file instead.')
      dump_index(EMPTY_INDEX, REMOTE_SYNC_FILE)
      sftp.put(REMOTE_SYNC_FILE, SYNC_FILE)
    remote_index = load_index(REMOTE_SYNC_FILE)
    local_index = load_index(SYNC_FILE)
    sync_recursive(sftp, local_index['.'], remote_index['.'], '')
    sftp.put(SYNC_FILE, SYNC_FILE)
  print('done.')


# os remove directory recursive python
import shutil

def remote_to_local(sftp, path, local_index, remote_index):
  if exists(local_index) and not exists(remote_index):
    print(f'deleting from local: {path}')
    if os.path.isfile(path) or os.path.islink(path):
      os.remove(path)
    if os.path.isdir(path):
      shutil.rmtree(path)
  else:
    print(f'downloading from remote: {path}')
    if sftp.isfile(path):
      sftp.get(path, path)
    if sftp.isdir(path):
      sftp.get_r(path, os.path.join(*path_split(path)[:-1]))
  update_index(SYNC_FILE, path)

def local_to_remote(sftp, path, local_index, remote_index):
  if exists(remote_index) and not exists(local_index):
    print(f'deleting from remote: {path}')
    if sftp.isfile(path):
      sftp.remove(path)
    if sftp.isdir(path):
      # https://stackoverflow.com/questions/44151259/is-it-possible-to-remove-directory-with-some-contents-using-pysftp-module
      # hacky solution...
      sftp.execute('rm -rf ' + os.path.join(REMOTE_CWD, path).replace(' ', '\\ '))
      # sftp.rmdir(remote)
  else:
    print(f'uploading to remote: {path}')
    if os.path.isfile(path) or os.path.islink(path):
      sftp.put(path, path)
    if os.path.isdir(path):
      try:
        sftp.mkdir(path)
      except IOError:
        pass
      sftp.put_r(path, path)
  update_index(SYNC_FILE, path)



def sync_recursive(sftp, local_index, remote_index, path):
  def create_file(data, time):
    file = {}
    file[SYNC_TIME] = time
    file[SYNC_DATA] = data
    return file

  # python union of two lists: https://www.pythonpool.com/python-union-of-lists/
  for key in set().union(local_index.keys(), remote_index.keys()):
    if key in [SYNC_DATA, SYNC_TIME]: continue

    full_path = os.path.join('.', path, key)

    if key not in local_index:
      local_index[key] = create_file(None, 0)
    if key not in remote_index:
      remote_index[key] = create_file(None, 0)

    if is_directory(local_index[key]) and is_directory(remote_index[key]):
      sync_recursive(sftp, local_index[key], remote_index[key], os.path.join(path, key))
    elif has_data_changed(local_index[key], remote_index[key]):
      local_sync_time = local_index[key][SYNC_TIME]
      remote_sync_time = remote_index[key][SYNC_TIME]
      if local_sync_time < remote_sync_time:
        remote_to_local(sftp, full_path, local_index[key], remote_index[key])
      else:
        local_to_remote(sftp, full_path, local_index[key], remote_index[key])


class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    if event.event_type not in ['modified', 'deleted', 'created']: return
    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    update_index(SYNC_FILE, event.src_path)



def watching():
  print()
  print('watching for changes and updating index automatically.')
  print('run again with `index` as parameter to force-update the index.')
  print('run again with `sync` as parameter to sync files with remote.')
  print()

def usage():
  print('parameter parsing failed. exiting.')

if len(sys.argv) == 1:
  watching()
  observer = Observer()
  observer.schedule(Handler(), '.', recursive=True)
  observer.start()
  try:
    while True:
      time.sleep(1)
  except KeyboardInterrupt:
    observer.stop()
    observer.join()
elif len(sys.argv) == 2:
  if sys.argv[1] == 'sync':
    sync_with_remote()
  elif sys.argv[1] == 'index':
    update_index_recursive()
  else:
    usage()
else:
  usage()
