"""
profile-svc — KMS envelope encryption for OAuth provider tokens.

Pattern per plan §10.1:
1. kms:GenerateDataKey → plaintext DEK + ciphertext
2. AES-256-GCM encrypt with DEK, random 12-byte IV, provider-specific AAD
3. Store: iv (12b) || ciphertext || tag (16b) in bytea; DEK ciphertext separately
4. Decrypt: kms:Decrypt(DEK ciphertext) → plaintext DEK → AES-GCM decrypt
5. Never log tokens; scrub *_token/*_secret in Sentry

Tokens are never returned over API — only provider_handle/scopes/sync_state.
"""

from __future__ import annotations

import os
import struct
from functools import lru_cache

import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _kms_client():
    return boto3.client("kms", region_name=os.environ.get("AWS_REGION", "us-east-1"))


def _kms_key_id() -> str:
    from app.config import get_settings
    return get_settings().kms_key_id_tokens


# ---------------------------------------------------------------------------
# Envelope encryption
# ---------------------------------------------------------------------------

class TokenCiphertext:
    """Holder for the encrypted token blob."""
    __slots__ = ("ciphertext", "data_key_ciphertext")

    def __init__(self, ciphertext: bytes, data_key_ciphertext: bytes) -> None:
        self.ciphertext = ciphertext  # iv(12) || ciphertext || tag(16)
        self.data_key_ciphertext = data_key_ciphertext


def encrypt_token(
    plaintext: str,
    provider: str,
    profile_id: str,
    token_kind: str,  # "access" | "refresh"
) -> TokenCiphertext:
    """Encrypt a token string using KMS envelope encryption."""
    kms = _kms_client()
    resp = kms.generate_data_key(
        KeyId=_kms_key_id(),
        KeySpec="AES_256",
    )
    plaintext_dek: bytes = resp["Plaintext"]
    data_key_ciphertext: bytes = resp["CiphertextBlob"]

    try:
        iv = os.urandom(12)
        aad = f"{provider}:{profile_id}:{token_kind}".encode()
        aesgcm = AESGCM(plaintext_dek)
        encrypted = aesgcm.encrypt(iv, plaintext.encode("utf-8"), aad)
        # encrypted = ciphertext + 16-byte tag (cryptography lib appends tag)
        blob = iv + encrypted
        return TokenCiphertext(ciphertext=blob, data_key_ciphertext=data_key_ciphertext)
    finally:
        # Zero the DEK from memory (best-effort in Python)
        plaintext_dek = b"\x00" * len(plaintext_dek)


def decrypt_token(
    ciphertext: bytes,
    data_key_ciphertext: bytes,
    provider: str,
    profile_id: str,
    token_kind: str,
) -> str:
    """Decrypt a token blob using KMS envelope decryption."""
    kms = _kms_client()
    resp = kms.decrypt(
        CiphertextBlob=data_key_ciphertext,
        KeyId=_kms_key_id(),
    )
    plaintext_dek: bytes = resp["Plaintext"]

    try:
        iv = ciphertext[:12]
        encrypted = ciphertext[12:]  # ciphertext + tag
        aad = f"{provider}:{profile_id}:{token_kind}".encode()
        aesgcm = AESGCM(plaintext_dek)
        return aesgcm.decrypt(iv, encrypted, aad).decode("utf-8")
    finally:
        plaintext_dek = b"\x00" * len(plaintext_dek)
