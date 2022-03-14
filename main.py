# python watchdog: https://www.geeksforgeeks.org/create-a-watchdog-in-python-to-look-for-filesystem-changes/
# python pysftp: https://appdividend.com/2020/06/08/python-sftp-how-to-access-sftp-server-using-pysftp/
# https://pysftp.readthedocs.io/en/release_0.2.8/pysftp.html
# https://stackoverflow.com/questions/38939454/verify-host-key-with-pysftp

from multiprocessing.sharedctypes import Value
import os
import re
import sys
import time
import json
import copy
import pysftp
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from FileSystem import LocalFileSystem, SSHFileSystem
from FileSystem import LOCKFILE as SYNC_LOCKFILE


SYNC_DIR_AS_FILE = ['node_modules', 'target']
SYNC_IGNORE = ['.next']


SYNC_FILE = '.sync'
SYNC_DATA = '.sd'
SYNC_TIME = '.st'
SYNC_IGNORE += [SYNC_FILE, SYNC_LOCKFILE]

def get_ms():
  # https://www.geeksforgeeks.org/get-current-time-in-milliseconds-using-python/
  return round(time.time() * 1)

def path_split(path):
  return path.split('/')

EMPTY_INDEX = {'.': {SYNC_TIME: get_ms()}}

def index_is_file(index, name):
  if name in SYNC_DIR_AS_FILE: return True
  return index_exists(index) and index[SYNC_DATA] == 1
def index_is_directory(index, name):
  if name in SYNC_DIR_AS_FILE: return False
  return index_exists(index) and index[SYNC_DATA] == 0
def index_exists(index):
  return SYNC_DATA in index and index[SYNC_DATA] is not None
def index_has_data_changed(index1, index2):
  return index1[SYNC_TIME] != index2[SYNC_TIME]

def index_create_file(data, time):
  file = {}
  file[SYNC_TIME] = time
  file[SYNC_DATA] = data
  return file

def get_file_data(path):
  split_path = path_split(path)
  if not os.path.exists(path):
    return index_create_file(None, get_ms())
  if os.path.isfile(path) or os.path.islink(path) or split_path[-1] in SYNC_DIR_AS_FILE:
    return index_create_file(1, get_ms())
  if os.path.isdir(path):
    return index_create_file(0, get_ms())
  print(f'DEBUG: could not get file data: {path}. file is assumed deleted')
  return index_create_file(None, get_ms())


def load_index(path):
  try:
    if not os.path.exists(path):
      with open(path, 'w') as f:
        f.write(json.dumps(EMPTY_INDEX))

    with open(path, 'r') as f:
      return json.loads(f.read())
  except:
    print(f'ERROR: could not load index: {path}')
    raise Exception("could not load index")

def dump_index(index, path):
  try:
    # https://stackoverflow.com/questions/16311562/python-json-without-whitespaces
    with open(path, 'w') as f:
      f.write(json.dumps(index, separators=(',', ':')))
  except:
    print(f'WARNING: could not dump index: {path}')


def update_index_recursively():
  # https://stackoverflow.com/questions/19587118/iterating-through-directories-with-python
  # https://stackoverflow.com/questions/7201203/python-current-directory-in-an-os-walk
  print('updating index recursively...')
  full_path = os.getcwd() + '/'
  index = EMPTY_INDEX
  for subdir, dirs, files in os.walk(full_path):
    for file in files:
      subdir = subdir.replace(full_path, '', 1)
      path = os.path.join('.', subdir, file)
      if index_is_safe(path_split(path)): update_index(index, path, get_file_data(path))
  dump_index(index, SYNC_FILE)
  print('done.')

def index_is_safe(path):
  if len(path) == 1 and path[0] == '.': return False
  for ignore in SYNC_IGNORE:
    if ignore in path: return False
  return True

def update_index(index, path, file_data):
  path = path_split(path)

  for name in path[:-1]:
    if name in SYNC_DIR_AS_FILE:
      return

  filename = path[-1]
  subdirectories = path[:-1]

  current_index = index
  for subdirectory in subdirectories:
    if subdirectory not in current_index: current_index[subdirectory] = {}
    current_index[subdirectory][SYNC_TIME] = file_data[SYNC_TIME]
    current_index[subdirectory][SYNC_DATA] = 0
    current_index = current_index[subdirectory]

  # https://stackoverflow.com/questions/38987/how-do-i-merge-two-dictionaries-in-a-single-expression-take-union-of-dictionari
  if filename not in current_index: current_index[filename] = {}
  current_index[filename] = {**current_index[filename], **file_data}

def sync_with_remote(source, destination):
  print('syncing files...')

  try:
    destination_index = json.loads(destination.read_file(SYNC_FILE))
  except FileNotFoundError:
    print('ERROR: destination index not found. execute deamon script to initialize working directory. aborting.')
    return
  
  try:
    source_index = json.loads(source.read_file(SYNC_FILE))
  except FileNotFoundError:
    print('ERROR: source index not found. execute deamon script to initialize working directory. aborting.')
    return

  err = None
  source.lock()
  destination.lock()

  try:
    sync_recursive(source, source_index, source_index['.'], destination, destination_index, destination_index['.'], '')
  except BaseException as e:
    err = e

  source.unlock()
  destination.unlock()
  if err: raise err

  print('updating source index...')
  source.write_file(SYNC_FILE, json.dumps(source_index, separators=(',', ':')))
  print('updating destination index...')
  destination.write_file(SYNC_FILE, json.dumps(source_index, separators=(',', ':')))

  print('done.')


def sync_recursive(source, source_index, source_index_curr, destination, destination_index, destination_index_curr, path):
  # python union of two lists: https://www.pythonpool.com/python-union-of-lists/
  for key in set().union(source_index_curr.keys(), destination_index_curr.keys()):
    if key in [SYNC_DATA, SYNC_TIME]: continue

    full_path = os.path.join('.', path, key)

    if key not in source_index_curr:
      source_index_curr[key] = index_create_file(None, 0)
    if key not in destination_index_curr:
      destination_index_curr[key] = index_create_file(None, 0)

    if index_is_directory(source_index_curr[key], key) and index_is_directory(destination_index_curr[key], key):
      sync_recursive(source, source_index, source_index_curr[key], destination, destination_index, destination_index_curr[key], os.path.join(path, key))
    elif index_has_data_changed(source_index_curr[key], destination_index_curr[key]):
      source_sync_time = source_index_curr[key][SYNC_TIME]
      destination_sync_time = destination_index_curr[key][SYNC_TIME]
      if source_sync_time < destination_sync_time:
        # destination to source
        if not index_exists(destination_index_curr[key]):
          print(f'delete src: {full_path}')
          source.remove(full_path)
        else:
          print(f'dst to src: {full_path}')
          source.from_local_path(destination.to_local_path(full_path), full_path)
        update_index(source_index, full_path, destination_index_curr[key])
      if source_sync_time > destination_sync_time:
        # source to destination
        if not index_exists(source_index_curr[key]):
          print(f'delete dst: {full_path}')
          destination.remove(full_path)
        else:
          print(f'src to dst: {full_path}')
          destination.from_local_path(source.to_local_path(full_path), full_path)
        update_index(destination_index, full_path, source_index_curr[key])


index = None
last_index = None
is_sync_lockfile_present = None

class Handler(FileSystemEventHandler):
  @staticmethod
  def on_any_event(event):
    global index
    global is_sync_lockfile_present
    # https://stackoverflow.com/questions/24597025/using-python-watchdog-to-monitor-a-folder-but-when-i-rename-a-file-i-havent-b
    # https://stackoverflow.com/questions/3167154/how-to-split-a-dos-path-into-its-components-in-python
    if path_split(event.src_path)[-1] == SYNC_LOCKFILE:
      if event.event_type in ['created', 'modified']:
        print('index lockfile got created. ignoring all changes to file system.')
        is_sync_lockfile_present = True
      if event.event_type in ['deleted', 'moved']:
        print('index lockfile got deleted. watching for changes to file system.')
        is_sync_lockfile_present = False
        index = load_index(SYNC_FILE)
    if not is_sync_lockfile_present:
      if event.event_type in ['modified', 'deleted', 'created', 'moved']:
        if index_is_safe(path_split(event.src_path)): 
          if event.event_type in ['modified'] and get_file_data(event.src_path) == 0: return # file modified inside directory
          # print(f'updating index: {event.src_path}')
          update_index(index, event.src_path, get_file_data(event.src_path))
      if event.event_type in ['moved']:
        if index_is_safe(path_split(event.dest_path)):
          # print(f'updating index: {event.dest_path}')
          update_index(index, event.dest_path, get_file_data(event.dest_path))
    else:
      if index_is_safe(path_split(event.src_path)):
        print(f'DEBUG: modification to file system was ignored: {event.src_path}')


def safe_deepcopy(dict):
  while True:
    try:
      return copy.deepcopy(dict)
    except:
      print('WARNING: error deepcopying index. trying again...')
      time.sleep(.1)

def watching():
  print()
  if is_sync_lockfile_present: print('index lockfile exists. ignoring all changes to file system.')
  else: print('watching for changes and updating index automatically.')
  print('run again with `index` as parameter to force-update the index.')
  print('run again with `sync <source> <destination>` as parameter to sync files.')
  print()

def usage():
  print('parameter parsing failed. exiting.')
  exit(1)

def parse_SSH_path(argument):
  # https://stackoverflow.com/questions/10059673/named-regular-expression-group-pgroup-nameregexp-what-does-p-stand-for
  credentials = re.search(r'(?P<username>.+?)@(?P<host>.+?):(?P<port>.+?)/(?P<path>.+)', argument)
  if credentials is None: return None

  credentials = credentials.groupdict()
  credentials['path'] = '/' + credentials['path']
  try:
    credentials['port'] = int(credentials['port'])
  except ValueError:
    return None


  cnopts = pysftp.CnOpts()
  cnopts.hostkeys = None   
  cnopts.compression = True
  credentials['cnopts'] = cnopts

  return credentials

def parse_local_path(argument):
  return { 'path': os.path.abspath(argument) }

def get_filesystem(argument):
  config = parse_SSH_path(argument)
  if config is not None: return SSHFileSystem(config)

  config = parse_local_path(argument)
  if config is not None: return LocalFileSystem(config)

  return None


if len(sys.argv) == 1:
  index = load_index(SYNC_FILE)
  is_sync_lockfile_present = os.path.exists(SYNC_LOCKFILE)

  watching()

  if not os.path.exists(SYNC_FILE):
    print('working directory initialized with empty index.')
    dump_index(EMPTY_INDEX, SYNC_FILE)

  observer = Observer()
  observer.schedule(Handler(), '.', recursive=True)
  observer.start()

  try:
    while True:
      if index != last_index:
        last_index = safe_deepcopy(index)
        dump_index(index, SYNC_FILE)
      time.sleep(1)
  except KeyboardInterrupt:
    print('exiting...')
    dump_index(index, SYNC_FILE)
    observer.stop()
    observer.join()

elif len(sys.argv) == 2:
  if sys.argv[1] == 'index':
    update_index_recursively()
  else:
    usage()

elif len(sys.argv) == 4:
  if sys.argv[1] == 'sync':
    source = get_filesystem(sys.argv[2])
    destination = get_filesystem(sys.argv[3])

    sync_with_remote(source, destination)

else:
  usage()
