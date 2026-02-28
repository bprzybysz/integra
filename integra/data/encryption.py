"""age encryption/decryption helpers using pyrage."""

from __future__ import annotations

import json
import logging
from typing import Any

import pyrage
import pyrage.x25519

logger = logging.getLogger(__name__)


def encrypt_data(plaintext: bytes, recipient_public_key: str) -> bytes:
    """Encrypt bytes using age recipient public key."""
    recipient = pyrage.x25519.Recipient.from_str(recipient_public_key)
    result: bytes = pyrage.encrypt(plaintext, [recipient])
    return result


def decrypt_data(ciphertext: bytes, identity_private_key: str) -> bytes:
    """Decrypt age-encrypted bytes using identity (private key)."""
    identity = pyrage.x25519.Identity.from_str(identity_private_key)
    result: bytes = pyrage.decrypt(ciphertext, [identity])
    return result


def encrypt_record(data: dict[str, Any], recipient_key: str) -> bytes:
    """Serialize a dict to JSON and encrypt it."""
    plaintext = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    return encrypt_data(plaintext, recipient_key)


def decrypt_record(ciphertext: bytes, identity_key: str) -> dict[str, Any]:
    """Decrypt age-encrypted bytes and deserialize as JSON dict."""
    plaintext = decrypt_data(ciphertext, identity_key)
    result: dict[str, Any] = json.loads(plaintext.decode("utf-8"))
    return result
