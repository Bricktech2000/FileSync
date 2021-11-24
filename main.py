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
REMOTE_SYNC_PATH = os.path.join(LOCAL_DIRECTORY, SYNC_FILE)
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
  return isinstance(tree[SYNC_DATA], str) and exists(tree)
def is_directory(tree):
  return SYNC_DATA is True and exists(tree)
def exists(tree):
  return tree[SYNC_DATA] is not None
def has_data_changed(tree1, tree2):
  return tree1[SYNC_DATA] != tree2[SYNC_DATA] or is_directory(tree1[SYNC_DATA]) or is_directory(tree2[SYNC_DATA])


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

def update_tree_recursive():
  # https://stackoverflow.com/questions/19587118/iterating-through-directories-with-python
  # https://stackoverflow.com/questions/7201203/python-current-directory-in-an-os-walk
  print('updating index recursively.')
  full_path = os.getcwd() + '/'
  for subdir, dirs, files in os.walk(full_path):
    for file in files:
      update_tree_safe(LOCAL_SYNC_PATH, [LOCAL_DIRECTORY] + path_split(os.path.join(subdir.replace(full_path, '', 1), file)))
  print('done.')

def update_tree_safe(sync_path, path):
    if len(path) == 1 and path[0] == '.': return
    if len(path) > 1 and path[1] == '.git': return
    if SYNC_FILE in path: return
    if LOCAL_REMOTE_SYNC_FILE in path: return
    update_tree(sync_path, path)


def update_tree(sync_path, path):
  file_hash = get_file_hash(os.path.join(*path))
  filename = path[-1]
  subdirectories = path[:-1]

  tree = load_tree(sync_path)
  current_tree = tree
  for subdirectory in subdirectories:
    if subdirectory not in current_tree: current_tree[subdirectory] = {}
    current_tree[subdirectory][SYNC_TIME] = get_ms()
    current_tree[subdirectory][SYNC_DATA] = True
    current_tree = current_tree[subdirectory]

  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  if filename not in current_tree: current_tree[filename] = {}
  current_tree[filename][SYNC_DATA] = file_hash
  current_tree[filename][SYNC_TIME] = get_ms()

  dump_tree(tree, sync_path)

def sync_with_remote():
  print('syncing files with remote.')
  if not UPLOAD_TO_REMOTE: return

  with pysftp.Connection(**REMOTE) as sftp:
    sftp.chdir(REMOTE_DIRECTORY)
    try:
      sftp.get(REMOTE_SYNC_PATH, LOCAL_REMOTE_SYNC_PATH)
    except FileNotFoundError:
      print('warning: remote sync file not found. uploading empty sync file instead.')
      dump_tree(EMPTY_TREE, LOCAL_REMOTE_SYNC_PATH)
      sftp.put(LOCAL_REMOTE_SYNC_PATH, REMOTE_SYNC_PATH)
    remote_tree = load_tree(LOCAL_REMOTE_SYNC_PATH)
    local_tree = load_tree(LOCAL_SYNC_PATH)
    sync_recursive(sftp, local_tree[LOCAL_DIRECTORY], remote_tree[LOCAL_DIRECTORY], '')
    sftp.put(LOCAL_REMOTE_SYNC_PATH, REMOTE_SYNC_PATH)
    # print('put', LOCAL_REMOTE_SYNC_PATH, REMOTE_SYNC_PATH)
  print('done.')


# os remove directory recursive python
import shutil
def remove_local(sftp, path, remote):
  print(f'remove local {path}')
  if os.path.isfile(path) or os.path.islink(path):
    os.remove(path)
  if os.path.isdir(path):
    shutil.rmtree(path)
  update_tree(LOCAL_SYNC_PATH, path_split(path))

def transfer_local(sftp, path, remote):
  print(f'transfer local {path}')
  if sftp.isfile(remote):
    sftp.get(remote, path)
  if sftp.isdir(remote):
    sftp.get_r(remote, os.path.join(*path_split(path)[:-1]))
  update_tree(LOCAL_SYNC_PATH, path_split(path))

def remove_remote(sftp, path, remote):
  print(f'remove remote {remote}')
  if sftp.isfile(remote):
    sftp.remove(remote)
  if sftp.isdir(remote):
    # https://stackoverflow.com/questions/44151259/is-it-possible-to-remove-directory-with-some-contents-using-pysftp-module
    # hacky solution...
    sftp.execute('rm -rf ' + os.path.join(REMOTE_DIRECTORY, remote).replace(' ', '\\ '))
    # sftp.rmdir(remote)
  update_tree(LOCAL_REMOTE_SYNC_PATH, path_split(path))

def transfer_remote(sftp, path, remote):
  print(f'transfer remote {path}')
  if os.path.isfile(path) or os.path.islink(path):
    sftp.put(path, remote)
  if os.path.isdir(path):
    try:
      sftp.mkdir(remote)
    except IOError:
      pass
    sftp.put_r(path, remote)
  update_tree(LOCAL_REMOTE_SYNC_PATH, path_split(path))

def remote_to_local(sftp, local_path, remote_path, local_tree, remote_tree):
  if exists(local_tree) and not exists(remote_tree):
    remove_local(sftp, local_path, remote_path)
  else:
    transfer_local(sftp, local_path, remote_path)

def local_to_remote(sftp, local_path, remote_path, local_tree, remote_tree):
  if exists(remote_tree) and not exists(local_tree):
    remove_remote(sftp, local_path, remote_path)
  else:
    transfer_remote(sftp, local_path, remote_path)



def tree_create_file(data, time):
  file = {}
  file[SYNC_TIME] = time
  file[SYNC_DATA] = data
  return file


def sync_recursive(sftp, local_tree, remote_tree, path):
  # python union of two lists: https://www.pythonpool.com/python-union-of-lists/
  for key in set().union(local_tree.keys(), remote_tree.keys()):
    if key in [SYNC_DATA, SYNC_TIME]: continue

    local_path = os.path.join(LOCAL_DIRECTORY, path)
    remote_path = os.path.join(LOCAL_DIRECTORY, path)
    local_path_key = os.path.join(local_path, key)
    remote_path_key = os.path.join(remote_path, key)

    if key not in local_tree:
      # print('notinlocal', local_tree, key, remote_tree, key)
      local_tree[key] = tree_create_file(None, 0)
      # update_tree(LOCAL_SYNC_PATH, path_split(local_path_key))
    if key not in remote_tree:
      # print('notinremote', local_tree, key, remote_tree, key)
      remote_tree[key] = tree_create_file(None, 0)
      # update_tree(LOCAL_REMOTE_SYNC_PATH, path_split(remote_path_key))

    if is_directory(local_tree[key]) and is_directory(remote_tree[key]):
      sync_recursive(sftp, local_tree[key], remote_tree[key], os.path.join(path, key))
    elif has_data_changed(local_tree[key], remote_tree[key]):
      local_sync_time = local_tree[key][SYNC_TIME]
      remote_sync_time = remote_tree[key][SYNC_TIME]
      if local_sync_time < remote_sync_time:
        remote_to_local(sftp, local_path_key, remote_path_key, local_tree[key], remote_tree[key])
      else:
        local_to_remote(sftp, local_path_key, remote_path_key, local_tree[key], remote_tree[key])


class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    # print('event: ', event.event_type, event.src_path)
    split_path = path_split(event.src_path)
    if event.event_type not in ['modified', 'deleted', 'created']: return
    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    # print('udpate: ', event.src_path)
    update_tree_safe(LOCAL_SYNC_PATH, split_path)



observer = Observer()
observer.schedule(Handler(), LOCAL_DIRECTORY, recursive=True)
observer.start()

try:
  print('watching for changes and updating index automatically.')
  print('press Enter to sync files with remote based on current index.')
  print('send `r` to force-update the index and sync files with remote.')
  print()
  while True:
    if UPLOAD_TO_REMOTE:
      if input() == 'r': update_tree_recursive()
      sync_with_remote()
    else:
      time.sleep(1)
except KeyboardInterrupt:
  observer.stop()
  observer.join()
