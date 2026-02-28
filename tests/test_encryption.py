"""Tests for integra.data.encryption."""

from __future__ import annotations

import pyrage
import pyrage.x25519
import pytest

from integra.data.encryption import (
    decrypt_data,
    decrypt_record,
    encrypt_data,
    encrypt_record,
)


@pytest.fixture
def age_keypair() -> tuple[str, str]:
    """Generate a fresh age keypair (public, private)."""
    identity = pyrage.x25519.Identity.generate()
    recipient = identity.to_public()
    return str(recipient), str(identity)


class TestEncryptDecryptData:
    def test_roundtrip(self, age_keypair: tuple[str, str]) -> None:
        pub, priv = age_keypair
        plaintext = b"hello world"
        ciphertext = encrypt_data(plaintext, pub)
        assert ciphertext != plaintext
        assert decrypt_data(ciphertext, priv) == plaintext

    def test_empty_bytes(self, age_keypair: tuple[str, str]) -> None:
        pub, priv = age_keypair
        ciphertext = encrypt_data(b"", pub)
        assert decrypt_data(ciphertext, priv) == b""

    def test_wrong_key_raises(self, age_keypair: tuple[str, str]) -> None:
        pub, _priv = age_keypair
        other_identity = pyrage.x25519.Identity.generate()
        ciphertext = encrypt_data(b"secret", pub)
        with pytest.raises(pyrage.DecryptError):
            decrypt_data(ciphertext, str(other_identity))


class TestEncryptDecryptRecord:
    def test_roundtrip(self, age_keypair: tuple[str, str]) -> None:
        pub, priv = age_keypair
        record = {"name": "test", "value": 42, "nested": {"a": 1}}
        ciphertext = encrypt_record(record, pub)
        assert decrypt_record(ciphertext, priv) == record

    def test_unicode(self, age_keypair: tuple[str, str]) -> None:
        pub, priv = age_keypair
        record = {"text": "zażółć gęślą jaźń"}
        assert decrypt_record(encrypt_record(record, pub), priv) == record

    def test_wrong_key_raises(self, age_keypair: tuple[str, str]) -> None:
        pub, _priv = age_keypair
        other_identity = pyrage.x25519.Identity.generate()
        ciphertext = encrypt_record({"x": 1}, pub)
        with pytest.raises(pyrage.DecryptError):
            decrypt_record(ciphertext, str(other_identity))
