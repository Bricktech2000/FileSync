# python watchdog: https://www.geeksforgeeks.org/create-a-watchdog-in-python-to-look-for-filesystem-changes/
# python pysftp: https://appdividend.com/2020/06/08/python-sftp-how-to-access-sftp-server-using-pysftp/
# https://pysftp.readthedocs.io/en/release_0.2.8/pysftp.html
# https://stackoverflow.com/questions/38939454/verify-host-key-with-pysftp

import os
import time
import json
import pysftp
import hashlib
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


LOCAL_DIRECTORY = '.'
REMOTE = {
  'host': 'admin-bricktech2000.emilien.ca',
  'port': 55522,
  'username': 'server',
  'private_key': '~/.ssh/id_rsa'
}
REMOTE_DIRECTORY = '/home/server/Files/'
BUF_SIZE = 65536
UPLOAD_TO_REMOTE = True

SYNC_FILE = '.sync'
LOCAL_REMOTE_SYNC_FILE = '.sync.remote'
LOCAL_SYNC_PATH = os.path.join(LOCAL_DIRECTORY, SYNC_FILE)
REMOTE_SYNC_PATH = os.path.join(REMOTE_DIRECTORY, SYNC_FILE)
LOCAL_REMOTE_SYNC_PATH = os.path.join(LOCAL_DIRECTORY, LOCAL_REMOTE_SYNC_FILE)
cnopts = pysftp.CnOpts()
cnopts.hostkeys = None   
REMOTE['cnopts'] = cnopts
SYNC_DATA = '.sync.data'
SYNC_TIME = '.sync.time'

def get_ms():
  return round(time.time() * 1000)

def path_split(path):
  return path.split('/')

def is_file(tree):
  return SYNC_DATA in tree

def is_file_deleted(tree):
  return tree[SYNC_DATA] == None

EMPTY_TREE = {'.': {SYNC_TIME: get_ms()}}

def load_tree(path):
  if not os.path.exists(path):
    with open(path, 'w') as f:
      f.write(json.dumps(EMPTY_TREE))

  with open(path, 'r') as f:
    return json.loads(f.read())

def dump_tree(tree, path):
  with open(path, 'w') as f:
    f.write(json.dumps(tree))

def get_file_hash(path):
  sha1 = hashlib.sha1()
  sha1.update(path.encode('utf-8'))
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

def update_tree(path):
  file_hash = get_file_hash(os.path.join(*path))
  filename = path[-1]
  subdirectories = path[:-1]

  tree = load_tree(LOCAL_SYNC_PATH)
  tree_current = tree
  for subdirectory in subdirectories:
    if subdirectory not in tree_current: tree_current[subdirectory] = {}
    tree_current[subdirectory][SYNC_TIME] = get_ms()
    tree_current = tree_current[subdirectory]

  if filename not in tree_current: tree_current[filename] = {}
  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  tree_current[filename][SYNC_DATA] = file_hash
  tree_current[filename][SYNC_TIME] = get_ms()

  dump_tree(tree, LOCAL_SYNC_PATH)

def sync_with_remote():
  if not UPLOAD_TO_REMOTE: return

  with pysftp.Connection(**REMOTE) as sftp:
    try:
      sftp.get(REMOTE_SYNC_PATH, LOCAL_REMOTE_SYNC_PATH)
    except FileNotFoundError:
      print('warning: remote sync file not found. uploading empty sync file instead.')
      dump_tree(EMPTY_TREE, LOCAL_REMOTE_SYNC_PATH)
      sftp.put(LOCAL_REMOTE_SYNC_PATH, REMOTE_SYNC_PATH)
    remote_tree = load_tree(LOCAL_REMOTE_SYNC_PATH)
    local_tree = load_tree(LOCAL_SYNC_PATH)
    sync_recursive(sftp, local_tree[LOCAL_DIRECTORY], remote_tree[LOCAL_DIRECTORY], '')
  print('done.')


def remove_local_file(path):
  print(f'remove local {path}')
  if os.path.exists(path):
    os.remove(path)
  else:
    update_tree(path_split(path))

def add_local_file(sftp, path, remote):
  print(f'add local {path}')
  try:
    try:
      sftp.get(path, remote)
    except IOError:
      try:
        os.mkdir(path)
      except IOError:
        pass
      sftp.get_r(path, LOCAL_DIRECTORY)
  except FileNotFoundError:
    pass

def remove_remote_file(sftp, remote):
  print(f'remove remote {remote}')
  try:
    sftp.remove(remote)
  except FileNotFoundError:
    print('TODO: remote file does not exist')

def add_remote_file(sftp, path, remote):
  print(f'add remote {path}')
  try:
    try:
      sftp.put(path, remote)
    except IOError:
      try:
        sftp.mkdir(remote)
      except IOError:
        pass
      print(path, remote)
      sftp.put_r(path, remote)
  except FileNotFoundError:
    update_tree(path_split(path))



def sync_recursive(sftp, local_tree, remote_tree, path):
  # python union of two lists: https://www.pythonpool.com/python-union-of-lists/
  for key in set().union(local_tree.keys(), remote_tree.keys()):
    if key in [SYNC_DATA, SYNC_TIME]: continue

    local_path = os.path.join(LOCAL_DIRECTORY, path)
    remote_path = os.path.join(REMOTE_DIRECTORY, path)
    local_path_key = os.path.join(local_path, key)
    remote_path_key = os.path.join(remote_path, key)

    if key not in local_tree:
      local_tree[key] = {}
      if SYNC_DATA in remote_tree[key]: local_tree[key][SYNC_DATA] = None
      local_tree[key][SYNC_TIME] = 0
    if key not in remote_tree:
      remote_tree[key] = {}
      if SYNC_DATA in local_tree[key]: remote_tree[key][SYNC_DATA] = None
      remote_tree[key][SYNC_TIME] = 0

    if is_file(local_tree[key]) or is_file(remote_tree[key]):
      print(key, local_tree[key], remote_tree[key])
      if local_tree[key][SYNC_DATA] != remote_tree[key][SYNC_DATA]:
        # if the data has changed
        local_sync_time = local_tree[key][SYNC_TIME]
        remote_sync_time = remote_tree[key][SYNC_TIME]
        if local_sync_time < remote_sync_time:
          if is_file(remote_tree[key]) and is_file_deleted(remote_tree[key]):
            remove_local_file(sftp, local_path_key)
          else:
            add_local_file(sftp, local_path_key, remote_path_key)
        else:
          if is_file(local_tree[key]) and is_file_deleted(local_tree[key]):
            remove_remote_file(sftp, remote_path_key)
          else:
            add_remote_file(sftp, local_path_key, remote_path_key)
    else: # both items are directories
      sync_recursive(sftp, local_tree[key], remote_tree[key], os.path.join(path, key))



class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    split_path = path_split(event.src_path)
    if event.event_type not in ['modified', 'deleted', 'created']: return
    if event.is_directory: return
    if '.git' in split_path: return
    if SYNC_FILE in split_path: return
    if LOCAL_REMOTE_SYNC_FILE in split_path: return

    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    update_tree(split_path)



observer = Observer()
observer.schedule(Handler(), LOCAL_DIRECTORY, recursive=True)
observer.start()

try:
  while True:
    if UPLOAD_TO_REMOTE:
      input()
      sync_with_remote()
    else:
      time.sleep(1)
except KeyboardInterrupt:
  observer.stop()
  observer.join()
