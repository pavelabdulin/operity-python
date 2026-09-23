"""Keys and request signing, per Operity's wire format.

An agent signs every request with its Ed25519 key. The signature covers:

    METHOD \\n PATH \\n TIMESTAMP \\n NONCE \\n sha256(BODY) as lowercase hex

where PATH is the raw path exactly as sent — percent-encoding untouched — with
no query string, TIMESTAMP is milliseconds since the epoch, and BODY is the
exact bytes on the wire. This module is an independent implementation: it
imports nothing from the server, and is held to the committed test vectors
rather than to the server's code, so the two cannot drift together.
"""

import base64
import hashlib
import secrets
import time
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class Keypair:
    """An agent's Ed25519 keypair. The private half never leaves this object
    unless you ask for the seed to store it yourself."""

    def __init__(self, private_key: Ed25519PrivateKey):
        self._private = private_key

    @classmethod
    def generate(cls) -> "Keypair":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed(cls, seed: bytes) -> "Keypair":
        if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
            raise ValueError("an Ed25519 seed is exactly 32 bytes")
        return cls(Ed25519PrivateKey.from_private_bytes(bytes(seed)))

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self._private.public_key().public_bytes_raw()).decode()

    def seed_bytes(self) -> bytes:
        """The 32-byte seed, for you to store. Treat it as the agent itself."""
        return self._private.private_bytes_raw()

    def sign(self, canonical: bytes) -> str:
        return base64.b64encode(self._private.sign(canonical)).decode()

    def __repr__(self) -> str:
        return f"Keypair(public_key={self.public_key_b64})"


def canonical_request(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    raw_path = path.split("?", 1)[0]
    digest = hashlib.sha256(body).hexdigest()
    return f"{method}\n{raw_path}\n{timestamp}\n{nonce}\n{digest}".encode()


def signed_headers(agent_id: str, keypair: Keypair, method: str, path: str, body: bytes,
                   timestamp: str | None = None, nonce: str | None = None) -> dict:
    timestamp = timestamp if timestamp is not None else str(int(time.time() * 1000))
    nonce = nonce if nonce is not None else str(uuid.UUID(bytes=secrets.token_bytes(16), version=4))
    return {
        "X-Operity-Agent": str(agent_id),
        "X-Operity-Timestamp": timestamp,
        "X-Operity-Nonce": nonce,
        "X-Operity-Signature": keypair.sign(canonical_request(method, path, timestamp, nonce, body)),
    }
