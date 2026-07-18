from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class VaultError(RuntimeError):
    """Raised when local secret storage cannot be opened safely."""


class SecretsVault:
    """Small encrypted-at-rest vault for a single local founder.

    The vault file and master key live in the local data directory and are never
    returned by the API. A production multi-user deployment needs a managed
    KMS; MorrowHelm's first version intentionally keeps the trust boundary local.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.key_path = self.data_dir / "master.key"
        self.vault_path = self.data_dir / "secrets.bin"
        self._fernet = Fernet(self._load_or_create_key())

    def _load_or_create_key(self) -> bytes:
        configured = os.getenv("MORROWHELM_MASTER_KEY")
        if configured:
            return configured.encode()
        if self.key_path.exists():
            return self.key_path.read_bytes().strip()
        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        try:
            self.key_path.chmod(0o600)
        except OSError:
            pass
        return key

    def _read(self) -> dict[str, str]:
        if not self.vault_path.exists():
            return {}
        try:
            return json.loads(self._fernet.decrypt(self.vault_path.read_bytes()))
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise VaultError("The local secret vault could not be decrypted") from exc

    def _write(self, values: dict[str, str]) -> None:
        encrypted = self._fernet.encrypt(json.dumps(values, sort_keys=True).encode())
        self.vault_path.write_bytes(encrypted)
        try:
            self.vault_path.chmod(0o600)
        except OSError:
            pass

    def set(self, connection_id: str, secret: str) -> None:
        values = self._read()
        values[connection_id] = secret
        self._write(values)

    def delete(self, connection_id: str) -> None:
        values = self._read()
        values.pop(connection_id, None)
        self._write(values)

    def get(self, connection_id: str) -> str | None:
        return self._read().get(connection_id)

    def has(self, connection_id: str) -> bool:
        return connection_id in self._read()
