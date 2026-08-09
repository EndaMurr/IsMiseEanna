import asyncio
import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from ismiseeanna_mcp.auth import WorkOSTokenVerifier

AUTHKIT_DOMAIN = "https://example-project.authkit.app"
RESOURCE_URL = "https://ismiseeanna.example.com/mcp"


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


@pytest.fixture(scope="module")
def other_keypair():
    """A second, unrelated key pair used to simulate a forged signature."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _make_token(private_key, **overrides):
    now = int(time.time())
    claims = {
        "iss": AUTHKIT_DOMAIN,
        "aud": RESOURCE_URL,
        "sub": "user_123",
        "client_id": "client_abc",
        "scope": "read write",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


@pytest.fixture
def verifier(monkeypatch, keypair):
    _private_key, public_key = keypair
    v = WorkOSTokenVerifier(AUTHKIT_DOMAIN, RESOURCE_URL)
    monkeypatch.setattr(
        v._jwks_client,
        "get_signing_key_from_jwt",
        lambda token: _FakeSigningKey(public_key),
    )
    return v


def test_strips_trailing_slash_from_domain():
    v = WorkOSTokenVerifier(AUTHKIT_DOMAIN + "/", RESOURCE_URL)
    assert v.authkit_domain == AUTHKIT_DOMAIN


def test_accepts_valid_token(verifier, keypair):
    private_key, _ = keypair
    token = _make_token(private_key)

    access_token = _run(verifier.verify_token(token))

    assert access_token is not None
    assert access_token.client_id == "client_abc"
    assert access_token.subject == "user_123"
    assert access_token.scopes == ["read", "write"]
    assert access_token.resource == RESOURCE_URL


def test_rejects_wrong_issuer(verifier, keypair):
    private_key, _ = keypair
    token = _make_token(private_key, iss="https://not-our-authkit.authkit.app")

    assert _run(verifier.verify_token(token)) is None


def test_rejects_wrong_audience(verifier, keypair):
    """A token minted for a different resource server must not verify here -
    this is the audience-confusion case that makes tokens non-replayable
    across deployments."""
    private_key, _ = keypair
    token = _make_token(private_key, aud="https://some-other-mcp-server.example.com/mcp")

    assert _run(verifier.verify_token(token)) is None


def test_rejects_expired_token(verifier, keypair):
    private_key, _ = keypair
    now = int(time.time())
    token = _make_token(private_key, iat=now - 600, exp=now - 300)

    assert _run(verifier.verify_token(token)) is None


def test_rejects_forged_signature(verifier, other_keypair):
    """Signed by a key the verifier doesn't trust - the JWKS lookup in the
    real flow would never return this key, but PyJWT must independently
    reject a mismatched signature regardless."""
    forged_private_key, _ = other_keypair
    token = _make_token(forged_private_key)

    assert _run(verifier.verify_token(token)) is None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def test_rejects_alg_none_token(verifier):
    """Guards against algorithm-confusion / 'alg: none' attacks: even if an
    attacker crafts a token claiming no signature is needed, the verifier
    pins RS256 and must not accept it."""
    now = int(time.time())
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64url(
        json.dumps(
            {"iss": AUTHKIT_DOMAIN, "aud": RESOURCE_URL, "iat": now, "exp": now + 300}
        ).encode()
    )
    unsigned = f"{header}.{payload}."

    assert _run(verifier.verify_token(unsigned)) is None


def test_rejects_garbage_token(verifier):
    assert _run(verifier.verify_token("not-a-jwt-at-all")) is None


def test_falls_back_to_sub_when_client_id_missing(verifier, keypair):
    private_key, _ = keypair
    token = _make_token(private_key, client_id=None)

    access_token = _run(verifier.verify_token(token))

    assert access_token is not None
    assert access_token.client_id == "user_123"


def test_scope_claim_as_list(verifier, keypair):
    private_key, _ = keypair
    token = _make_token(private_key, scope=None, scp=["read", "write"])

    access_token = _run(verifier.verify_token(token))

    assert access_token is not None
    assert access_token.scopes == ["read", "write"]
