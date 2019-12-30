from abc import abstractmethod

from mycloud.mycloudapi.helper import (get_object_id,
                                       raise_if_invalid_drive_path)
from mycloud.mycloudapi.requests import ContentType, Method, MyCloudRequest

REQUEST_URL = 'https://storage.prod.mdl.swisscom.ch/object?p='


class ObjectRequest(MyCloudRequest):

    def __init__(self, object_resource: str):
        raise_if_invalid_drive_path(object_resource)
        self.object_resource = object_resource

    def get_request_url(self):
        return REQUEST_URL + get_object_id(self.object_resource)

    @abstractmethod
    def get_method(self):
        return None


class PutObjectRequest(ObjectRequest):

    def __init__(self, object_resource: str, generator):
        super().__init__(object_resource)
        self.generator = generator

    def get_method(self):
        return Method.PUT

    def get_data_generator(self):
        return self.generator

    def get_content_type(self):
        return ContentType.APPLICATION_OCTET_STREAM


class GetObjectRequest(ObjectRequest):

    def __init__(self, object_resource: str):
        super().__init__(object_resource)

    def get_method(self):
        return Method.GET

    def is_query_parameter_access_token(self):
        return True


class DeleteObjectRequest(ObjectRequest):

    def get_method(self):
        return Method.DELETE

    @staticmethod
    def is_success(resp):
        return resp.status == 204
