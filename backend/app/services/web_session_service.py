import hashlib
import secrets
import time
from functools import lru_cache

from app.core.config import Settings
from app.repositories.web_session import WebSessionStore


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@lru_cache(maxsize=8)
def credential_fingerprint(username: str, password: str) -> str:
    return hashlib.pbkdf2_hmac('sha256', password.encode(), ('edgeml-web:' + username).encode(), 600_000).hex()


class WebSessionService:
    def __init__(self, settings: Settings, repository: WebSessionStore):
        self.settings = settings
        self.repository = repository

    def credential(self) -> str:
        return credential_fingerprint(self.settings.web_username, self.settings.web_password or '')

    def login(self, username: str, password: str, client: str):
        if not self.settings.web_password:
            raise RuntimeError('Web login is not configured. Set EDGEML_WEB_PASSWORD on the server.')
        now = time.time()
        if not self.repository.reserve_attempt(client, now):
            raise TimeoutError('Too many login attempts. Try again in five minutes.')
        # Compare fixed-length digests; never store submitted login passwords.
        if not (secrets.compare_digest(digest(username), digest(self.settings.web_username))
                & secrets.compare_digest(digest(password), digest(self.settings.web_password))):
            raise ValueError('Invalid username or password.')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.repository.create(digest(token), csrf, self.credential(), now + self.settings.web_session_seconds, now)
        return token, csrf

    def authenticate(self, token: str):
        if not token or not self.settings.web_password:
            return None
        row = self.repository.get(digest(token))
        if row and row['expires'] > time.time() and secrets.compare_digest(row['credential'], self.credential()):
            return row
        return None

    def logout(self, token: str):
        self.repository.delete(digest(token))
