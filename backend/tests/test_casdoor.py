"""Casdoor pilot only logs in identities explicitly bound to a local account."""

import pytest
import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jose import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1 import casdoor
from app.core.config import settings
from app.models.user import User


PAYLOAD = {
    "code": "one-use-code",
    "code_verifier": "v" * 43,
    "nonce": "n" * 32,
    "redirect_uri": "http://localhost:5173/auth/casdoor/callback",
}


@pytest.mark.asyncio
async def test_casdoor_login_requires_preprovisioned_binding(client, monkeypatch):
    http, _, engine = client
    monkeypatch.setattr(settings, "CASDOOR_ISSUER", "http://casdoor.test")
    async def verified(_body):
        return "stable-casdoor-subject"
    monkeypatch.setattr(casdoor, "_verified_subject", verified)

    unbound = await http.post("/api/v1/auth/casdoor/exchange", json=PAYLOAD)
    assert unbound.status_code == 403

    assert (await http.post("/api/v1/auth/casdoor/link", json=PAYLOAD)).status_code == 404
    Session = async_sessionmaker(engine, class_=AsyncSession)
    async with Session() as db:
        user = (await db.execute(select(User).where(User.username == "test-admin"))).scalar_one()
        user.casdoor_issuer = "http://casdoor.test"
        user.casdoor_subject = "stable-casdoor-subject"
        await db.commit()

    logged_in = await http.post("/api/v1/auth/casdoor/exchange", json=PAYLOAD)
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["user"]["role"] == "admin"
    assert logged_in.json()["access_token"]

    async with Session() as db:
        user = (await db.execute(select(User).where(User.username == "test-admin"))).scalar_one()
        assert user.casdoor_subject == "stable-casdoor-subject"
        assert user.token_version == 1
        await db.execute(update(User).where(User.id == user.id).values(is_active=False))
        await db.commit()
    disabled = await http.post("/api/v1/auth/casdoor/exchange", json=PAYLOAD)
    assert disabled.status_code == 403


def test_redirect_must_match_configured_origin_and_path(monkeypatch):
    monkeypatch.setattr(settings, "CASDOOR_REDIRECT_ORIGINS", "http://localhost:5173")
    assert casdoor._redirect_allowed("http://localhost:5173/auth/casdoor/callback")
    assert not casdoor._redirect_allowed("http://127.0.0.1:5173/auth/casdoor/callback")
    assert not casdoor._redirect_allowed("http://localhost:5173/elsewhere")
    assert not casdoor._redirect_allowed("http://localhost:5173/auth/casdoor/callback?next=bad")


@pytest.mark.asyncio
async def test_oidc_id_token_signature_audience_and_nonce_are_verified(monkeypatch):
    monkeypatch.setattr(settings, "CASDOOR_ISSUER", "http://casdoor.test")
    monkeypatch.setattr(settings, "CASDOOR_CLIENT_ID", "ticket-client")
    monkeypatch.setattr(settings, "CASDOOR_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(settings, "CASDOOR_REDIRECT_ORIGINS", "http://localhost:5173")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_numbers()
    encode_int = lambda n: __import__("base64").urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()
    jwks = {"keys": [{"kty": "RSA", "kid": "test", "use": "sig", "alg": "RS256", "n": encode_int(public.n), "e": encode_int(public.e)}]}
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    access_token = "example-casdoor-access-token"
    at_hash = __import__("base64").urlsafe_b64encode(__import__("hashlib").sha256(access_token.encode()).digest()[:16]).rstrip(b"=").decode()
    claims = {"iss": "http://casdoor.test", "sub": "casdoor-admin", "aud": "ticket-client", "nonce": PAYLOAD["nonce"], "at_hash": at_hash, "exp": 9999999999}
    issued_token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": "http://casdoor.test",
                "authorization_endpoint": "http://casdoor.test/login/oauth/authorize",
                "token_endpoint": "http://casdoor.test/api/login/oauth/access_token",
                "jwks_uri": "http://casdoor.test/.well-known/jwks",
            })
        if request.url.path == "/api/login/oauth/access_token":
            return httpx.Response(200, json={"id_token": issued_token, "access_token": access_token})
        return httpx.Response(200, json=jwks)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(casdoor.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler)))
    body = casdoor.ExchangeRequest(**PAYLOAD)
    assert await casdoor._verified_subject(body) == "casdoor-admin"
    body.nonce = "wrong-nonce-value-123456"
    with pytest.raises(Exception) as exc:
        await casdoor._verified_subject(body)
    assert getattr(exc.value, "status_code", None) == 401
    body.nonce = PAYLOAD["nonce"]
    issued_token = jwt.encode({**claims, "aud": "another-client"}, private_pem, algorithm="RS256", headers={"kid": "test"})
    with pytest.raises(Exception) as exc:
        await casdoor._verified_subject(body)
    assert getattr(exc.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_password_login_requires_matching_bound_subject(client, monkeypatch):
    http, _, engine = client
    monkeypatch.setattr(settings, "CASDOOR_ISSUER", "http://casdoor.test")
    monkeypatch.setattr(settings, "CASDOOR_CLIENT_ID", "ticket-client")
    monkeypatch.setattr(settings, "CASDOOR_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(settings, "CASDOOR_REDIRECT_ORIGINS", "http://localhost:5173")
    Session = async_sessionmaker(engine, class_=AsyncSession)
    async with Session() as db:
        user = (await db.execute(select(User).where(User.username == "test-dispatcher"))).scalar_one()
        user.casdoor_issuer = "http://casdoor.test"
        user.casdoor_subject = "bound-subject"
        await db.commit()

    async def correct(_username, _password):
        return "bound-subject"
    from app.api.v1 import auth
    monkeypatch.setattr(auth, "verify_password_subject", correct)
    payload = {"username": "test-dispatcher", "password": "casdoor-password"}
    good = await http.post("/api/v1/auth/login", json=payload)
    assert good.status_code == 200, good.text
    assert good.json()["user"]["username"] == "test-dispatcher"

    async def wrong(_username, _password):
        return "different-subject"
    monkeypatch.setattr(auth, "verify_password_subject", wrong)
    denied = await http.post("/api/v1/auth/login", json=payload)
    assert denied.status_code == 401
    missing = await http.post("/api/v1/auth/login", json={"username": "missing", "password": "anything"})
    assert missing.status_code == 401
