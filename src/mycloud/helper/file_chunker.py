import math, os
from io import BytesIO, RawIOBase
from mycloudapi import ObjectResourceBuilder


MY_CLOUD_BIG_FILE_CHUNK_SIZE = 5120000


class FileChunker:
    def __init__(self, full_file_path):
        self.full_file_path = full_file_path
        self.stream = None
        self.is_final = False
        self.chunk_num = 0

    
    def get_next_chunk(self):
        self.__initialize_stream()
        if self.is_final:
            return None
        reader = StreamReader(self.stream, self, self.chunk_num)
        self.chunk_num += 1
        return reader


    def set_is_final(self):
        self.is_final = True


    def close(self):
        if self.stream:
            self.stream.close()


    def __initialize_stream(self):
        if self.stream is None:
            self.stream = open(self.full_file_path, 'rb')


class StreamReader:
    def __init__(self, stream: RawIOBase, file_chunker: FileChunker, chunk: int):
        self.stream = stream
        self.read_length = 0
        self.file_chunker = file_chunker
        self.stream.seek(chunk * MY_CLOUD_BIG_FILE_CHUNK_SIZE, 0)


    def read(self, length: int):
        if self.read_length == MY_CLOUD_BIG_FILE_CHUNK_SIZE:
            return None
        elif self.read_length > MY_CLOUD_BIG_FILE_CHUNK_SIZE:
            raise ValueError('Read length must exactly match big cloud file chunk size')
        read = self.stream.read(length)
        if len(read) != length:
            self.file_chunker.set_is_final()
        self.read_length += length
        return read