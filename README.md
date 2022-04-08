# FileSync

A symmetrical decentralized file syncing system

## Overview

FileSync is a program that synchronizes different file systems without a central authority. It keeps track of all file system changes in an index file `.sync`. When a synchronization is requested by a system, it uses SFTP to download the remote's index file, compares both index files to identify differences, and updates both file systems with the latest changes.

## Requirements

- Python 3

## Initial Setup

1. Install dependencies: `pip install watchdog pysftp`
2. Make sure to be able to login to the remote machine through SSH without a password. To do so, set up SSH public key authentication and add the remote machine to the known hosts file (or type in _yes_ when connecting using OpenSSH for the first time)
3. `cd` to root of the directory you wish to sync and run `python3 main.py index` if it isn't empty.
4. Run `python3 main.py &` to watch for changes and to update the index automatically.
5. After some changes have been made, run `python3 main.py sync . user@ip_address:port/path/to/remote/directory` to sync them with a remote machine.

## Usage

Run `python3 main.py & ` to watch for changes and to update the index automatically. This deamon should constantly be running to allow the program to keep track file system events.

Run `python3 main.py index` to force-update the index. This must be run when syncing a new root directory if it isn't empty, or if the index file becomes corrupt.

Run `python3 main.py sync <source> <destination>` to sync two file sytems together. This command has to be run manually for the syncing to happen. Note that `<source>` and `<destination>` may either be a local relative path (i.e. `.`), a local absolute path (i.e. `/home/user/`), or a remote absolute path (i.e. `user@ip_address:port/path/to/remote/directory`). When using a remote path, make sure to have SSH key authentication set up on the remote machine.
