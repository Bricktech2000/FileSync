# python watchdog: https://www.geeksforgeeks.org/create-a-watchdog-in-python-to-look-for-filesystem-changes/
# python pysftp: https://ourcodeworld.com/articles/read/813/how-to-access-a-sftp-server-using-pysftp-in-python

import os
import time
import json
import pysftp
import hashlib
from datetime import date, datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


LOCAL_DIRECTORY = '.'
REMOTE = {
  'host': 'admin-bricktech2000.emilien.ca:55522',
  'port': '55522',
  'username': 'server'
}
REMOTE_DIRECTORY = '~/Files/'
BUF_SIZE = 65536
LOCAL_SYNC_PATH = os.path.join(LOCAL_DIRECTORY, '.sync')


def load_tree():
  if not os.path.exists(LOCAL_SYNC_PATH):
    with open(LOCAL_SYNC_PATH, 'w') as f:
      f.write('{}')

  with open(LOCAL_SYNC_PATH, 'r') as f:
    return json.loads(f.read())

def dump_tree(tree):
  with open(LOCAL_SYNC_PATH, 'w') as f:
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

  tree = load_tree()
  tree_current = tree
  for subdirectory in subdirectories:
    if subdirectory not in tree_current: tree_current[subdirectory] = {}
    tree_current = tree_current[subdirectory]

  if filename not in tree_current: tree_current[filename] = {}
  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  tree_current[filename]['.sync.data'] = file_hash
  tree_current[filename]['.sync.time'] = round(time.time() * 1000)

  dump_tree(tree)

# def sync_files():
  # tree = load_tree()


class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    # if event.is_directory:
      # print('directory')
    if event.event_type not in ['modified', 'deleted', 'created']: return
    if event.is_directory: return
    if '.git' in event.src_path.split('/'): return
    if '.sync' in event.src_path.split('/'): return
    path = event.src_path

    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    hash = get_file_hash(path)
    update_tree(os.path.split(path))
    print("'{}' modified with hash: {}".format(path, hash))


observer = Observer()
observer.schedule(Handler(), LOCAL_DIRECTORY, recursive=True)
observer.start()

try:
  while True:
    time.sleep(1)
except KeyboardInterrupt:
  observer.stop()
  observer.join()
















