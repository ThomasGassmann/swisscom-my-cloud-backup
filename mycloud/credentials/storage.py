import asyncio
import json
import logging
import os

import keyring

from mycloud.constants import AUTHENTICATION_INFO_LOCATION, SERVICE_NAME
from mycloud.mycloudapi.auth import get_bearer_token


class CredentialStorage:

    def __init__(self):
        pass

    @classmethod
    async def save(cls, username: str, password: str, skip_validation: bool = False, no_headless_validation: bool = False) -> bool:
        validation_result = True if skip_validation else await _validate_credentials(username, password, not no_headless_validation)
        if not validation_result:
            return False

        with open(AUTHENTICATION_INFO_LOCATION, 'w') as file:
            json.dump({
                'user': username
            }, file)
        keyring.set_password(SERVICE_NAME, username, password)
        return True

    @classmethod
    def load(cls):
        if not os.path.isfile(AUTHENTICATION_INFO_LOCATION):
            return None, None
        with open(AUTHENTICATION_INFO_LOCATION, 'r') as file:
            auth_info = json.load(file)
        return cls.load_with_user(auth_info['user'])

    @classmethod
    def load_with_user(cls, user):
        password = keyring.get_password(SERVICE_NAME, user)
        return (user, password)

    @classmethod
    async def validate(cls, user, password):
        return await _validate_credentials(user, password, True)


async def _validate_credentials(user_name: str, password: str, headless: bool) -> bool:
    try:
        await get_bearer_token(user_name, password, headless)
        return True
    except ValueError:
        return False
