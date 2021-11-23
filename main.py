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

LOCAL_SYNC_PATH = os.path.join(LOCAL_DIRECTORY, '.sync')
REMOTE_SYNC_PATH = os.path.join(REMOTE_DIRECTORY, '.sync')
LOCAL_REMOTE_SYNC_PATH = os.path.join(LOCAL_DIRECTORY, '.sync.remote')
cnopts = pysftp.CnOpts()
cnopts.hostkeys = None   
REMOTE['cnopts'] = cnopts

def get_ms():
  return round(time.time() * 1000)

def path_split(path):
  return path.split('/')

EMPTY_TREE = {'.': {'.sync.time': get_ms()}}

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
    tree_current[subdirectory]['.sync.time'] = get_ms()
    tree_current = tree_current[subdirectory]

  if filename not in tree_current: tree_current[filename] = {}
  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  tree_current[filename]['.sync.data'] = file_hash
  tree_current[filename]['.sync.time'] = get_ms()

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


def sync_recursive(sftp, local_tree, remote_tree, path):
  # python union of two lists: https://www.pythonpool.com/python-union-of-lists/
  for key in set().union(local_tree.keys(), remote_tree.keys()):
    if key in ['.sync.data', '.sync.time']: continue

    current_path = os.path.join(path, key)
    current_local_path = os.path.join(LOCAL_DIRECTORY, current_path)
    current_remote_path = os.path.join(REMOTE_DIRECTORY, current_path)
    if key not in local_tree:
          if '.sync.data' in remote_tree[key] and remote_tree[key]['.sync.data'] == None:
            print(f'remove local {current_local_path}')
            if os.path.exists(current_local_path):
              os.remove(current_local_path)
            else:
              update_tree(path_split(current_local_path))
            continue
          print(f'add local {current_local_path}')
          try:
            try:
              sftp.get(current_local_path, current_remote_path)
            except IOError:
              try:
                os.mkdir(current_local_path)
              except IOError:
                pass
              sftp.get_r(current_remote_path, LOCAL_DIRECTORY)
          except FileNotFoundError:
            pass
    elif key not in remote_tree:
          if '.sync.data' in local_tree[key] and local_tree[key]['.sync.data'] == None:
            print(f'remove remote {current_local_path}')
            try:
              sftp.remove(current_remote_path)
            except FileNotFoundError:
              print('TODO: remote file does not exist')
            continue
          print(f'add remote {current_local_path}')
          try:
            try:
              sftp.put(current_local_path, current_remote_path)
            except IOError:
              try:
                sftp.mkdir(current_remote_path)
              except IOError:
                pass
              sftp.put_r(current_local_path, current_remote_path)
          except FileNotFoundError:
            update_tree(path_split(current_local_path))
    elif '.sync.data' in local_tree[key] or '.sync.data' in remote_tree[key]:
      # at elast one of the items is a file
      if local_tree[key]['.sync.data'] != remote_tree[key]['.sync.data']:
        # if the data has changed
        local_sync_time = local_tree[key]['.sync.time']
        remote_sync_time = remote_tree[key]['.sync.time']
        if local_sync_time < remote_sync_time:
          if '.sync.data' in remote_tree[key] and remote_tree[key]['.sync.data'] == None:
            print(f'remove local {current_local_path}')
            if os.path.exists(current_local_path):
              os.remove(current_local_path)
            else:
              update_tree(path_split(current_local_path))
            continue
          print(f'add local {current_local_path}')
          try:
            try:
              sftp.get(current_local_path, current_remote_path)
            except IOError:
              try:
                os.mkdir(current_local_path)
              except IOError:
                pass
              sftp.get_r(current_remote_path, LOCAL_DIRECTORY)
          except FileNotFoundError:
            pass
        else:
          if '.sync.data' in local_tree[key] and local_tree[key]['.sync.data'] == None:
            print(f'remove remote {current_local_path}')
            try:
              sftp.remove(current_remote_path)
            except FileNotFoundError:
              print('TODO: remote file does not exist')
            continue
          print(f'add remote {current_local_path}')
          try:
            try:
              sftp.put(current_local_path, current_remote_path)
            except IOError:
              try:
                sftp.mkdir(current_remote_path)
              except IOError:
                pass
              sftp.put_r(current_local_path, current_remote_path)
          except FileNotFoundError:
            update_tree(path_split(current_local_path))
    else:
      # both items are directories
      sync_recursive(sftp, local_tree[key], remote_tree[key], current_path)



class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    if event.event_type not in ['modified', 'deleted', 'created']: return
    if event.is_directory: return
    if '.git' in event.src_path.split('/'): return
    if '.sync' in event.src_path.split('/'): return
    if '.sync.remote' in event.src_path.split('/'): return
    path = event.src_path

    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    update_tree(path_split(path))



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
















