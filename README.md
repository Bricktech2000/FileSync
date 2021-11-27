# FileSync

A symmetrical decentralized file syncing system

## Overview

FileSync is a program that synchronizes different file systems without a central authority. It keeps track of all file system changes in an index file `.sync`. When a synchronization is requested by a system, it uses SFTP to download the remote's index file, compares both index files to identify differences, and updates both file systems with the latest changes.

## Requirements

- Python 3

## Initial Setup

1. Install dependencies:

```bash
pip install watchdog pysftp
```

2. `cd` to root of the directory you wish to sync.

3. Edit `remote.json` with the credentials to a machine with SSH enabled.

4. Run `python3 main.py &` to watch for changes and to update the index automatically.

## Usage

Run `python3 main.py & ` to watch for changes and to update the index automatically. This should be constantly running to allow the program to keep track file system events.

Run `python3 main.py index` to force-update the index. This must be run when syncing a new root directory, or if the index file becomes corrupt.

Run `python3 main.py sync` to sync the files with the remote specified in `remote.json`. This command has to be run manually for the syncing to happen.
