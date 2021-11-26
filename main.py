# python watchdog: https://www.geeksforgeeks.org/create-a-watchdog-in-python-to-look-for-filesystem-changes/
# python pysftp: https://appdividend.com/2020/06/08/python-sftp-how-to-access-sftp-server-using-pysftp/
# https://pysftp.readthedocs.io/en/release_0.2.8/pysftp.html
# https://stackoverflow.com/questions/38939454/verify-host-key-with-pysftp

import os
import sys
import time
import json
import base64
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
SYNC_DATA = '.sd'
SYNC_TIME = '.st'

def get_ms():
  return round(time.time() * 1)

def path_split(path):
  return path.split('/')

def is_file(index):
  return isinstance(index[SYNC_DATA], str) and exists(index)
def is_directory(index):
  return index[SYNC_DATA] is True and exists(index)
def exists(index):
  return index[SYNC_DATA] is not None
def has_data_changed(index1, index2):
  if is_directory(index1) and is_directory(index2):
    return index1[SYNC_DATA] == None or index2[SYNC_DATA] == None
  return index1[SYNC_TIME] != index2[SYNC_TIME]


EMPTY_INDEX = {'.': {SYNC_TIME: get_ms()}}

def load_index(path):
  if not os.path.exists(path):
    with open(path, 'w') as f:
      f.write(json.dumps(EMPTY_INDEX))

  with open(path, 'r') as f:
    return json.loads(f.read())

def dump_index(index, path):
  # https://stackoverflow.com/questions/16311562/python-json-without-whitespaces
  with open(path, 'w') as f:
    f.write(json.dumps(index, separators=(',', ':')))

def get_file_data(path):
  if os.path.isdir(path):
    return 0
  if os.path.isfile(path) or os.path.islink(path):
    return 1
  if not os.path.exists(path):
    return None

def hash(input):
  # https://docs.python.org/3/library/hashlib.html
  sha256 = hashlib.sha256()
  sha256.update(input.encode('utf-8'))
  # only preserve 32 bits, remove trailing `=` signs
  # print(base64.b64encode(sha256.digest()[0:4])[:-2].decode('utf-8'))
  return base64.b64encode(sha256.digest()[0:4])[:-2].decode('utf-8')

def update_index_recursive():
  # https://stackoverflow.com/questions/19587118/iterating-through-directories-with-python
  # https://stackoverflow.com/questions/7201203/python-current-directory-in-an-os-walk
  print('updating index recursively...')
  full_path = LOCAL_CWD + '/'
  index = load_index(SYNC_FILE)
  for subdir, dirs, files in os.walk(full_path):
    for file in files:
      index = update_index(index, os.path.join('.', subdir.replace(full_path, '', 1), file))
  dump_index(index, SYNC_FILE)
  print('done.')

def is_safe(path):
  path = path_split(path)
  if len(path) == 1 and path[0] == '.': return False
  if len(path) > 1 and path[1] == '.git': return False
  # if '.mp4' in path[-1]: return index
  # if 'node_modules' in path: return index
  if SYNC_FILE in path: return False
  if REMOTE_SYNC_FILE in path: return False
  return True

def update_index(index, path):
  if not is_safe(path): return index
  path = path_split(path)

  file_data = get_file_data(os.path.join(*path))
  filename = path[-1]
  subdirectories = path[:-1]

  current_index = index
  for subdirectory in subdirectories:
    if hash(subdirectory) not in current_index: current_index[hash(subdirectory)] = {}
    current_index[hash(subdirectory)][SYNC_TIME] = get_ms()
    current_index[hash(subdirectory)][SYNC_DATA] = 0
    current_index = current_index[hash(subdirectory)]

  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  if filename not in current_index: current_index[hash(filename)] = {}
  current_index[hash(filename)][SYNC_DATA] = file_data
  current_index[hash(filename)][SYNC_TIME] = get_ms()

  return index

def sync_with_remote():
  print('syncing files with remote...')
  if not UPLOAD_TO_REMOTE: return

  with pysftp.Connection(**REMOTE) as sftp:
    sftp.chdir(REMOTE_CWD)
    print('fetching remote sync file...')
    try:
      sftp.get(SYNC_FILE, REMOTE_SYNC_FILE)
    except FileNotFoundError:
      print('warning: remote sync file not found. uploading empty sync file instead.')
      dump_index(EMPTY_INDEX, REMOTE_SYNC_FILE)
      sftp.put(REMOTE_SYNC_FILE, SYNC_FILE)
    remote_index = load_index(REMOTE_SYNC_FILE)
    local_index = load_index(SYNC_FILE)
    os.remove(REMOTE_SYNC_FILE)
    sync_recursive(sftp, local_index[hash('.')], remote_index[hash('.')], '')
    print('updating remote sync file...')
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
  dump_index(update_index(load_index(SYNC_FILE), path), SYNC_FILE)

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
  dump_index(update_index(load_index(SYNC_FILE), path), SYNC_FILE)



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

    if hash(key) not in local_index:
      local_index[hash(key)] = create_file(None, 0)
    if hash(key) not in remote_index:
      remote_index[hash(key)] = create_file(None, 0)

    elif has_data_changed(local_index[hash(key)], remote_index[hash(key)]):
      local_sync_time = local_index[hash(key)][SYNC_TIME]
      remote_sync_time = remote_index[hash(key)][SYNC_TIME]
      if local_sync_time < remote_sync_time:
        remote_to_local(sftp, full_path, local_index[hash(key)], remote_index[hash(key)])
      else:
        local_to_remote(sftp, full_path, local_index[hash(key)], remote_index[hash(key)])
    if is_directory(local_index[hash(key)]) and is_directory(remote_index[hash(key)]):
      sync_recursive(sftp, local_index[hash(key)], remote_index[hash(key)], os.path.join(path, key))


class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    # https://stackoverflow.com/questions/24597025/using-python-watchdog-to-monitor-a-folder-but-when-i-rename-a-file-i-havent-b
    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    if event.event_type in ['modified', 'deleted', 'created', 'moved']:
      if is_safe(event.src_path): 
        print(f'updating index: {event.src_path}')
        dump_index(update_index(load_index(SYNC_FILE), event.src_path), SYNC_FILE)
    if event.event_type in ['moved']:
      if is_safe(event.dest_path):
        print(f'updating index: {event.dest_path}')
        dump_index(update_index(load_index(SYNC_FILE), event.dest_path), SYNC_FILE)



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
