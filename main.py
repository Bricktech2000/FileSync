# python watchdog: https://www.geeksforgeeks.org/create-a-watchdog-in-python-to-look-for-filesystem-changes/
# python pysftp: https://appdividend.com/2020/06/08/python-sftp-how-to-access-sftp-server-using-pysftp/
# https://pysftp.readthedocs.io/en/release_0.2.8/pysftp.html
# https://stackoverflow.com/questions/38939454/verify-host-key-with-pysftp

import os
import sys
from threading import current_thread
import time
import json
import copy
import pysftp
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


with open('remote.json', 'r') as f:
  REMOTE = json.loads(f.read())

LOCAL_CWD = os.getcwd()
REMOTE_CWD = '/home/server/Files/'
BUF_SIZE = 65536
FOLDERS_AS_FILE = ['.next', 'node_modules', 'target']

SYNC_FILE = '.sync'
REMOTE_SYNC_FILE = '.sync.remote'
SYNC_LOCKFILE = '.sync.lock'
REMOTE_SYNC_LOCKFILE = '.sync.lock.remote'
cnopts = pysftp.CnOpts()
cnopts.hostkeys = None   
cnopts.compression = True
REMOTE['cnopts'] = cnopts
SYNC_DATA = '.sd'
SYNC_TIME = '.st'

def get_ms():
  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  return round(time.time() * 1)

def path_split(path):
  return path.split('/')

EMPTY_INDEX = {'.': {SYNC_TIME: get_ms()}}

def is_file(index, name):
  if name in FOLDERS_AS_FILE: return True
  return exists(index) and index[SYNC_DATA] == 1
def is_directory(index, name):
  if name in FOLDERS_AS_FILE: return False
  return exists(index) and index[SYNC_DATA] == 0
def exists(index):
  return SYNC_DATA in index and index[SYNC_DATA] is not None
def has_data_changed(index1, index2):
  return index1[SYNC_TIME] != index2[SYNC_TIME]

def create_file(data, time):
  file = {}
  file[SYNC_TIME] = time
  file[SYNC_DATA] = data
  return file
def get_file_data(path):
  split_path = path_split(path)
  if not os.path.exists(path):
    return create_file(None, get_ms())
  if os.path.isfile(path) or os.path.islink(path) or split_path[-1] in FOLDERS_AS_FILE:
    return create_file(1, get_ms())
  if os.path.isdir(path):
    return create_file(0, get_ms())
  print(f'debug: could not get file data: {path}. file is assumed deleted')
  return create_file(None, get_ms())



def load_index(path):
  try:
    if not os.path.exists(path):
      with open(path, 'w') as f:
        f.write(json.dumps(EMPTY_INDEX))

    with open(path, 'r') as f:
      return json.loads(f.read())
  except:
    print(f'error: could not load index: {path}')
    raise Exception("could not load index")

def dump_index(index, path):
  try:
    # https://stackoverflow.com/questions/16311562/python-json-without-whitespaces
    with open(path, 'w') as f:
      f.write(json.dumps(index, separators=(',', ':')))
  except:
    print(f'warning: could not dump index: {path}')


def update_index_recursive():
  # https://stackoverflow.com/questions/19587118/iterating-through-directories-with-python
  # https://stackoverflow.com/questions/7201203/python-current-directory-in-an-os-walk
  print('updating index recursively...')
  full_path = LOCAL_CWD + '/'
  index = EMPTY_INDEX
  for subdir, dirs, files in os.walk(full_path):
    for file in files:
      subdir = subdir.replace(full_path, '', 1)
      path = os.path.join('.', subdir, file)
      if is_safe(path_split(path)): update_index(index, path, get_file_data(path))
  dump_index(index, SYNC_FILE)
  print('done.')

def is_safe(path):
  if len(path) == 1 and path[0] == '.': return False
  # if '.mp4' in path[-1]: return index
  # if 'node_modules' in path: return index
  if SYNC_FILE in path: return False
  if REMOTE_SYNC_FILE in path: return False
  if SYNC_LOCKFILE in path: return False
  if REMOTE_SYNC_LOCKFILE in path: return False
  return True

def update_index(index, path, file_data):
  path = path_split(path)

  for name in path[:-1]:
    if name in FOLDERS_AS_FILE:
      return

  filename = path[-1]
  subdirectories = path[:-1]

  current_index = index
  for subdirectory in subdirectories:
    if subdirectory not in current_index: current_index[subdirectory] = {}
    current_index[subdirectory][SYNC_TIME] = file_data[SYNC_TIME]
    current_index[subdirectory][SYNC_DATA] = 0
    current_index = current_index[subdirectory]

  # if filename in current_index:
    # print(f'debug: filename already in index: {filename} with data: {current_index[filename]}')
    # print(f'debug: overriding file with data: { {**current_index[filename], **file_data} }')
  # https://stackoverflow.com/questions/38987/how-do-i-merge-two-dictionaries-in-a-single-expression-take-union-of-dictionari
  if filename not in current_index: current_index[filename] = {}
  current_index[filename] = {**current_index[filename], **file_data}

def sync_with_remote():
  print('syncing files with remote...')

  with pysftp.Connection(**REMOTE) as sftp:
    sftp.chdir(REMOTE_CWD)
    print('fetching remote sync file...')
    try:
      sftp.get(SYNC_FILE, REMOTE_SYNC_FILE)
    except FileNotFoundError:
      print('warning: remote sync file not found. uploading empty sync file instead.')
      dump_index(EMPTY_INDEX, REMOTE_SYNC_FILE)
      sftp.put(REMOTE_SYNC_FILE, SYNC_FILE)
    
    with open(SYNC_LOCKFILE, 'w') as f: pass
    sftp.put(SYNC_LOCKFILE, SYNC_LOCKFILE)

    local_index = load_index(SYNC_FILE)
    remote_index = load_index(REMOTE_SYNC_FILE)
    sync_recursive(sftp, local_index, local_index['.'], remote_index, remote_index['.'], '')
    dump_index(local_index, SYNC_FILE)
    dump_index(remote_index, REMOTE_SYNC_FILE)

    print('updating remote sync file...')
    sftp.put(REMOTE_SYNC_FILE, SYNC_FILE)
    os.remove(REMOTE_SYNC_FILE)
    sftp.remove(SYNC_LOCKFILE)
    os.remove(SYNC_LOCKFILE)

  time.sleep(.1)
  print('done.')


# os remove directory recursive python
import shutil

def remote_to_local(sftp, path, remote_index_curr, local_index):
  if not exists(remote_index_curr):
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
  update_index(local_index, path, remote_index_curr)

def local_to_remote(sftp, path, local_index_curr, remote_index):
  if not exists(local_index_curr):
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
  update_index(remote_index, path, local_index_curr)

def sync_recursive(sftp, local_index, local_index_curr, remote_index, remote_index_curr, path):
  # python union of two lists: https://www.pythonpool.com/python-union-of-lists/
  for key in set().union(local_index_curr.keys(), remote_index_curr.keys()):
    if key in [SYNC_DATA, SYNC_TIME]: continue

    full_path = os.path.join('.', path, key)

    if key not in local_index_curr:
      local_index_curr[key] = create_file(None, 0)
    if key not in remote_index_curr:
      remote_index_curr[key] = create_file(None, 0)

    if is_directory(local_index_curr[key], key) and is_directory(remote_index_curr[key], key):
      sync_recursive(sftp, local_index, local_index_curr[key], remote_index, remote_index_curr[key], os.path.join(path, key))
    elif has_data_changed(local_index_curr[key], remote_index_curr[key]):
      local_sync_time = local_index_curr[key][SYNC_TIME]
      remote_sync_time = remote_index_curr[key][SYNC_TIME]
      if local_sync_time < remote_sync_time:
        remote_to_local(sftp, full_path, remote_index_curr[key], local_index)
      else:
        local_to_remote(sftp, full_path, local_index_curr[key], remote_index)


index = load_index(SYNC_FILE)
last_index = copy.deepcopy(index)
is_sync_lockfile_present = os.path.exists(SYNC_LOCKFILE)

class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    global index
    global is_sync_lockfile_present
    # https://stackoverflow.com/questions/24597025/using-python-watchdog-to-monitor-a-folder-but-when-i-rename-a-file-i-havent-b
    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    if path_split(event.src_path)[-1] == SYNC_LOCKFILE:
      if event.event_type in ['created', 'modified']:
        print('sync lockfile got created. ignoring all changes to file system.')
        is_sync_lockfile_present = True
      if event.event_type in ['deleted', 'moved']:
        print('sync lockfile got deleted. watching for changes to file system.')
        is_sync_lockfile_present = False
        index = load_index(SYNC_FILE)
    if not is_sync_lockfile_present:
      if event.event_type in ['modified', 'deleted', 'created', 'moved']:
        if is_safe(path_split(event.src_path)): 
          if event.event_type in ['modified'] and get_file_data(event.src_path) == 0: return # file modified inside directory
          print(f'updating index: {event.src_path}')
          update_index(index, event.src_path, get_file_data(event.src_path))
      if event.event_type in ['moved']:
        if is_safe(path_split(event.dest_path)):
          print(f'updating index: {event.dest_path}')
          update_index(index, event.dest_path, get_file_data(event.dest_path))
    else:
      if is_safe(path_split(event.src_path)):
        print(f'debug: modification to file system was ignored: {event.src_path}')


def safe_deepcopy(dict):
  while True:
    try:
      return copy.deepcopy(dict)
    except:
      print('warning: error deepcopying index. trying again...')
      time.sleep(.1)

def watching():
  print()
  if is_sync_lockfile_present: print('sync lockfile exists. ignoring all changes to file system.')
  else: print('watching for changes and updating index automatically.')
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
      if index != last_index:
        last_index = safe_deepcopy(index)
        dump_index(index, SYNC_FILE)
      time.sleep(.1)
  except KeyboardInterrupt:
    print('exiting...')
    dump_index(index, SYNC_FILE)
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
