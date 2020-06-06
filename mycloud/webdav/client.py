import inject
import asyncio
import os
import threading
from typing import Dict
from enum import Enum
from mycloud.mycloudapi.requests.drive import MyCloudMetadata, FileEntry, DirEntry, PutObjectRequest
from mycloud.drive import DriveClient


class FileType(Enum):
    File = 0
    Dir = 1
    Enoent = 2


class WriterWithCallback:
    def __init__(self, initial, callback):
        self._initial = initial
        self._callback = callback

    def write(self, bytes):
        self._initial.write(bytes)

    def close(self):
        self._initial.close()
        self._callback()


class MyCloudDavClient:

    # make tree, update on other actions
    metadata_cache: Dict[str, MyCloudMetadata] = dict()
    # loops used to translate from sync to async paths
    # one per thread is needed
    loops: Dict[int, asyncio.AbstractEventLoop] = dict()
    drive_client: DriveClient = inject.attr(DriveClient)

    def _run_sync(self, task):
        thread_id = threading.get_ident()
        if thread_id in self.loops:
            loop = self.loops[thread_id]
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loops[thread_id] = loop

        return asyncio.get_event_loop().run_until_complete(task)

    def get_file_type(self, path: str):
        normed = os.path.normpath(path)
        if normed == '/':
            return FileType.Dir

        basename = os.path.basename(normed)
        try:
            metadata = self._get_metadata(os.path.dirname(normed))
            def contains(l): return any(
                filter(lambda x: x.name == basename, l))
            if contains(metadata.files):
                return FileType.File
            if contains(metadata.dirs):
                return FileType.Dir
            return FileType.Enoent
        except:
            return FileType.Enoent

    def get_directory_metadata(self, path):
        return self._get_metadata(path)

    def mkdirs(self, path):
        self._run_sync(self.drive_client.mkdirs(path))
        self._clear_cache(path)

    def open_read(self, path):
        return self._run_sync(self.drive_client.open_read(path))

    def open_write(self, path):
        temp = self._run_sync(self.drive_client.open_write(path))
        return WriterWithCallback(temp, lambda: self._clear_cache(path))

    def mkfile(self, path):
        self._run_sync(self.drive_client.mkfile(path))
        self._clear_cache(path)

    def remove(self, path, is_dir):
        self._run_sync(self.drive_client.delete(path, is_dir))
        self._clear_cache(path)

    def _clear_cache(self, path: str):
        dirname = os.path.dirname(path)
        normed = os.path.normpath(dirname)
        del self.metadata_cache[normed]

    def _get_metadata(self, path: str):
        path = os.path.normpath(path)
        if path in self.metadata_cache:
            return self.metadata_cache[path]
        metadata = self._run_sync(
            self.drive_client.get_directory_metadata(path))
        self.metadata_cache[path] = metadata
        return metadata
