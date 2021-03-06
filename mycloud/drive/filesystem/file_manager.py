import logging
import os
from collections import defaultdict
from pathlib import Path

from mycloud.common import is_int, operation_timeout
from mycloud.constants import METADATA_FILE_NAME, MY_CLOUD_BIG_FILE_CHUNK_SIZE
from mycloud.drive.filesystem.file_metadata import FileMetadata, Version
from mycloud.drive.filesystem.file_version import (CalculatableVersion,
                                                   HashCalculatedVersion)
from mycloud.drive.filesystem.metadata_manager import MetadataManager
from mycloud.drive.filesystem.translatable_path import (BasicRemotePath,
                                                        TranslatablePath)
from mycloud.drive.filesystem.versioned_stream_accessor import \
    VersionedCloudStreamAccessor
from mycloud.mycloudapi import MyCloudRequestExecutor
from mycloud.mycloudapi.requests.drive import (DirectoryListRequest, ListType,
                                               MetadataRequest)
from mycloud.drive.streamapi import (CloudStream, DownStream, DownStreamExecutor,
                                     ProgressReporter, UpStream, UpStreamExecutor)


class FileManager:

    def __init__(self, request_executor: MyCloudRequestExecutor, transforms, reporter: ProgressReporter):
        self._request_executor = request_executor
        self._transforms = transforms
        self._metadata_manager = MetadataManager(request_executor)
        self._reporter = ProgressReporter() if reporter is None else reporter

    async def read_directory(self,
                             translatable_path: TranslatablePath,
                             recursive=False,
                             deep=False,
                             _second=False):
        logging.debug(f'Reading directory...')
        data = None
        if deep:
            if not recursive:
                raise ValueError(
                    'Cannot perform non-recursive deep directory list using directory list request')
            logging.debug('Using directory list request...')
            data = self._read_directory_using_directory_list_request(
                translatable_path)
        else:
            logging.debug('Using metadata request...')
            data = self._read_directory_using_metadata_request(
                translatable_path, recursive, False)
        async for item in data:
            yield item

    async def started_partial_upload(self,
                                     translatable_path: TranslatablePath,
                                     calculatable_version: CalculatableVersion):
        versioned_stream_accessor = VersionedCloudStreamAccessor(
            translatable_path, calculatable_version, None)
        path = versioned_stream_accessor.get_base_path()
        metadata_request = MetadataRequest(path)
        response = await self._request_executor.execute(metadata_request)
        if response.result.status == 404:
            return False, 0
        (_, files) = await response.formatted()
        return True, len(files)

    async def started_partial_download(self,
                                       translatable_path: TranslatablePath,
                                       calculatable_version: CalculatableVersion,
                                       local_path: str):
        if not operation_timeout(lambda x: os.path.isfile(x['local_path']), local_path=local_path):
            return False, False, 0
        stats = operation_timeout(lambda x: os.stat(
            x['local_path']), local_path=local_path)
        file_length = stats.st_size
        metadata = await self.read_file_metadata(translatable_path)
        version = metadata.get_version(
            calculatable_version.calculate_version())
        parts = version.get_parts()
        directory = os.path.dirname(parts[0])
        metadata_request = MetadataRequest(directory)
        response = await self._request_executor.execute(metadata_request)
        (dirs, files) = await response.formatted()
        if any(dirs):
            raise ValueError(
                'Cannot have directories in directory of partial files')
        file_lengths = [file['Length'] for file in files]
        summed_up_size = sum(file_lengths)
        if file_length >= summed_up_size:
            return True, False, 0
        chunk_size = version.get_property(
            'chunk_size') or MY_CLOUD_BIG_FILE_CHUNK_SIZE
        if len(files) > 1:
            percent_diff = chunk_size / \
                max(file_lengths) if chunk_size > max(
                    file_lengths) else max(file_lengths) / chunk_size
            if percent_diff > 1.1:
                raise ValueError(
                    'Expected chunk size differs more than 10% from actual chunk size... Aborting')

        # Can't compare exact size because remote and local sizes are different
        hash_prop = version.get_property('hash')
        if hash_prop is None:
            return False, True, file_length // chunk_size

        local_hash = calculatable_version.get_hash() if isinstance(calculatable_version,
                                                                   HashCalculatedVersion) else HashCalculatedVersion(local_path).calculate_version()
        if local_hash == hash_prop:
            return True, False, 0
        return False, True, file_length // chunk_size

    async def read_file(self,
                        downstream: DownStream,
                        translatable_path: TranslatablePath,
                        calculatable_version: CalculatableVersion):
        metadata = await self._metadata_manager.get_metadata(translatable_path)
        calculated_version = calculatable_version.calculate_version()
        if not metadata.contains_version(calculated_version):
            raise ValueError('Version does not exist for given file')

        versioned_stream_accessor = self._prepare_versioned_stream(
            translatable_path, calculatable_version, downstream)
        downstreamer = DownStreamExecutor(
            self._request_executor, self._reporter)
        await downstreamer.download_stream(versioned_stream_accessor)

    async def read_file_metadata(self,
                                 translatable_path: TranslatablePath):
        metadata = await self._metadata_manager.get_metadata(translatable_path)
        return metadata

    async def write_file(self,
                         upstream: UpStream,
                         translatable_path: TranslatablePath,
                         calculatable_version: CalculatableVersion):
        existing_metadata = await self._metadata_manager.get_metadata(
            translatable_path)
        existing_metadata = existing_metadata if existing_metadata is not None else FileMetadata()
        version_identifier = calculatable_version.calculate_version()

        if existing_metadata.contains_version(version_identifier):
            raise ValueError('Version does already exist')

        versioned_stream_accessor = self._prepare_versioned_stream(
            translatable_path, calculatable_version, upstream)

        remote_base_path = translatable_path.calculate_remote()
        version = Version(version_identifier, remote_base_path)

        if upstream.continued_append_starting_index > 0:
            versioned_base_path = versioned_stream_accessor.get_base_path()
            list_directory_request = MetadataRequest(versioned_base_path)
            listed_directory = await self._request_executor.execute(
                list_directory_request)
            (dirs, files) = await listed_directory.formatted()
            if any(dirs):
                raise ValueError(
                    'A versioned directory with partial files cannot contain subdirectories')
            if len(files) != upstream.continued_append_starting_index:
                raise ValueError('Must append at correct position')
            for file in files:
                file_name = os.path.basename(file['Path'])
                path = Path(file_name).with_suffix('').stem
                if not is_int(path):
                    raise ValueError('Non-integer indexed part file found')
                version.add_part_file(file['Path'])

        upstreamer = UpStreamExecutor(self._request_executor, self._reporter)
        await upstreamer.upload_stream(versioned_stream_accessor)

        for transform in self._transforms:
            version.add_transform(transform.get_name())
        remote_properties = translatable_path.calculate_properties()

        for key in remote_properties:
            version.add_property(key, remote_properties[key])

        for accessed in versioned_stream_accessor.get_accessed_file_parts():
            version.add_part_file(accessed)
        existing_metadata.update_version(version)

        await self._metadata_manager.update_metadata(
            translatable_path, existing_metadata)

    def _prepare_versioned_stream(self, translatable_path: TranslatablePath, calculatable_version: CalculatableVersion, cloud_stream: CloudStream):
        versioned_cloud_stream_accessor = VersionedCloudStreamAccessor(
            translatable_path, calculatable_version, cloud_stream)
        for transform in self._transforms:
            versioned_cloud_stream_accessor.add_transform(transform)
        return versioned_cloud_stream_accessor

    async def _read_directory_using_metadata_request(self, translatable_path: TranslatablePath, recursive: bool, _second: bool):
        base = translatable_path.calculate_remote()
        metadata_request = MetadataRequest(base)
        response = await self._request_executor.execute(metadata_request)
        logging.debug(f'Got response for path {base}')
        if response.result.status == 404:
            return
        (dirs, files) = await response.formatted()
        if len(files) == 1 and files[0]['Name'] == METADATA_FILE_NAME:
            yield translatable_path

        async def loop_dirs(rec, sec):
            for directory in dirs:
                remote_path = BasicRemotePath(directory['Path'])
                data = self._read_directory_using_metadata_request(
                    remote_path, recursive=rec, _second=sec)
                async for item in data:
                    yield item

        items = loop_dirs(True, False) if recursive else await loop_dirs(False, True)
        async for item in items:
            yield item

    async def _read_directory_using_directory_list_request(self, translatable_path: TranslatablePath):
        remote_path = translatable_path.calculate_remote()
        directory_list_command = DirectoryListRequest(
            remote_path, ListType.File)
        response = await self._request_executor.execute(
            directory_list_command)
        if response.result.status == 404:
            return

        if DirectoryListRequest.is_timeout(response):
            metadata_request = MetadataRequest(remote_path)
            metadata_response = await self._request_executor.execute(
                metadata_request)
            (dirs, files) = await metadata_response.formatted()
            if len(files) == 1 and os.path.basename(files[0]) == METADATA_FILE_NAME:
                yield files[0]['Path']
                return

            for directory in dirs:
                dir_path = BasicRemotePath(directory['Path'])
                items = await self._read_directory_using_directory_list_request(dir_path)
                for item in items:
                    yield item
        else:
            files = await response.formatted()
            # TODO: use less memory and make proper use of `files` generator
            directory_file_count = defaultdict(int)
            for file in files:
                directory = os.path.dirname(file['Path'])
                directory_file_count[directory] += 1

            for file in files:
                file_name = os.path.basename(file['Path'])
                dir_name = os.path.dirname(file['Path'])
                if file_name == METADATA_FILE_NAME and directory_file_count[dir_name] == 1:
                    yield file['Path']
