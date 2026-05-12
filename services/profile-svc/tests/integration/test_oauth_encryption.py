"""
Tests: KMS token encryption round-trip (using moto mocked KMS).
Run: pytest tests/integration/test_oauth_encryption.py -q
"""

import os
import uuid

import boto3
import pytest

# Use moto for KMS mocking — no real AWS calls
try:
    from moto import mock_aws
    HAS_MOTO = True
except ImportError:
    HAS_MOTO = False

pytestmark = pytest.mark.skipif(not HAS_MOTO, reason="moto not installed")


@pytest.fixture(autouse=True)
def aws_credentials(monkeypatch):
    """Set up fake AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@mock_aws
def test_kms_encrypt_decrypt_round_trip():
    """Encrypt and decrypt a token; verify the plaintext is recovered."""
    from app.services.kms_crypto import decrypt_token, encrypt_token

    # Create a KMS key in moto
    kms = boto3.client("kms", region_name="us-east-1")
    key = kms.create_key(Description="test-key")
    key_id = key["KeyMetadata"]["KeyId"]

    # Override the KMS key ID in settings
    os.environ["KMS_KEY_ID_TOKENS"] = key_id

    plaintext = "access_token_value_abc123"
    provider = "instagram"
    profile_id = str(uuid.uuid4())
    token_kind = "access"

    ct = encrypt_token(plaintext, provider, profile_id, token_kind)
    assert ct.ciphertext
    assert ct.data_key_ciphertext
    # Ciphertext should not be the plaintext
    assert plaintext.encode() not in ct.ciphertext

    recovered = decrypt_token(ct.ciphertext, ct.data_key_ciphertext, provider, profile_id, token_kind)
    assert recovered == plaintext


@mock_aws
def test_kms_wrong_aad_fails():
    """Decryption with wrong AAD should fail (GCM authentication)."""
    from cryptography.exceptions import InvalidTag
    from app.services.kms_crypto import decrypt_token, encrypt_token

    kms = boto3.client("kms", region_name="us-east-1")
    key = kms.create_key(Description="test-key")
    key_id = key["KeyMetadata"]["KeyId"]
    os.environ["KMS_KEY_ID_TOKENS"] = key_id

    plaintext = "my_secret_token"
    profile_id = str(uuid.uuid4())

    ct = encrypt_token(plaintext, "instagram", profile_id, "access")

    # Try to decrypt with wrong provider — AAD mismatch → GCM tag fail
    with pytest.raises(Exception):
        decrypt_token(ct.ciphertext, ct.data_key_ciphertext, "spotify", profile_id, "access")


@mock_aws
def test_refresh_token_encrypted_separately():
    """Access and refresh tokens are encrypted independently."""
    from app.services.kms_crypto import decrypt_token, encrypt_token

    kms = boto3.client("kms", region_name="us-east-1")
    key = kms.create_key(Description="test-key")
    os.environ["KMS_KEY_ID_TOKENS"] = key["KeyMetadata"]["KeyId"]

    profile_id = str(uuid.uuid4())
    access_ct = encrypt_token("access_token", "youtube", profile_id, "access")
    refresh_ct = encrypt_token("refresh_token", "youtube", profile_id, "refresh")

    assert access_ct.ciphertext != refresh_ct.ciphertext

    access_plain = decrypt_token(access_ct.ciphertext, access_ct.data_key_ciphertext, "youtube", profile_id, "access")
    refresh_plain = decrypt_token(refresh_ct.ciphertext, refresh_ct.data_key_ciphertext, "youtube", profile_id, "refresh")

    assert access_plain == "access_token"
    assert refresh_plain == "refresh_token"
