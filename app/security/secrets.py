import os
import base64
from typing import Optional, Dict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from app.config import settings


class SecretManager:
    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._fernet: Optional[Fernet] = None
        self._init_encryption()

    def _init_encryption(self):
        key_file = os.path.join(os.path.dirname(settings.database_url.replace("sqlite+aiosqlite:///", "")), ".secret_key")
        password = os.environ.get("AGENT_MASTER_PASSWORD", "").encode()
        
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                key = f.read()
        else:
            if not password:
                password = os.urandom(32)
            salt = os.urandom(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
            with open(key_file, "wb") as f:
                f.write(key)
            os.chmod(key_file, 0o600)
        
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        if not self._fernet:
            raise RuntimeError("Encryption not initialized")
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, encrypted: str) -> str:
        if not self._fernet:
            raise RuntimeError("Encryption not initialized")
        return self._fernet.decrypt(encrypted.encode()).decode()

    def set_secret(self, key: str, value: str) -> None:
        self._cache[key] = self.encrypt(value)

    def get_secret(self, key: str) -> Optional[str]:
        if key in self._cache:
            return self.decrypt(self._cache[key])
        
        env_value = os.environ.get(key)
        if env_value:
            return env_value
        
        return None

    def delete_secret(self, key: str) -> bool:
        return self._cache.pop(key, None) is not None

    def get_api_key(self) -> Optional[str]:
        return self.get_secret("MODEL_API_KEY") or settings.model_api_key


secret_manager = SecretManager()