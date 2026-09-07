"""The deployment contract: secrets, and the config that carries them.

These are cheap tests for an expensive failure. A CRM that ships PAN and Aadhaar
encryption is only as good as the key management around it, and the ways that goes
wrong are boring: a variable the app needs that the compose file never passes, a
placeholder secret that a hurried deploy leaves in place, a key change that silently
turns stored ciphertext into garbage.

The `.env.example` / compose cross-check exists because exactly that bug shipped:
`PII_MASTER_KEY` was enforced by the application, set in neither compose file, and
mentioned in no example — a fresh `docker compose up` crashed with no clue why.
"""

import base64
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
COMPOSE_FILES = [REPO / "docker-compose.yml", REPO / "docker-compose.contabo.yml"]
ENV_EXAMPLE = REPO / "docker" / ".env.example"

#: Secrets a deployment must supply. Compose is expected to *refuse to start*
#: without these rather than fall back to a default, because a deployment quietly
#: running on a known secret is worse than one that will not come up.
REQUIRED_SECRETS = ["JWT_SECRET", "PII_MASTER_KEY", "ADMIN_PASSWORD"]


def _compose_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _referenced_env_vars(text: str) -> set[str]:
    """Every ${VAR...} the compose file interpolates from the host environment."""
    return set(re.findall(r"\$\{([A-Z0-9_]+)[:?}-]", text))


def _env_example_keys() -> set[str]:
    keys = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0])
    return keys


# --- the deployment contract --------------------------------------------------

@pytest.mark.parametrize("compose", COMPOSE_FILES, ids=lambda p: p.name)
def test_every_variable_compose_needs_is_in_the_env_example(compose):
    """Otherwise a deployment fails on a variable nobody documented."""
    if not compose.exists():
        pytest.skip(f"{compose.name} not present")
    referenced = _referenced_env_vars(_compose_text(compose))
    documented = _env_example_keys()
    missing = sorted(referenced - documented)
    assert not missing, f"{compose.name} reads {missing} but .env.example never mentions them"


@pytest.mark.parametrize("compose", COMPOSE_FILES, ids=lambda p: p.name)
def test_the_pii_master_key_reaches_the_backend(compose):
    """The application refuses to start in production without it — so it must be passed.

    This is the bug this file was written for: enforced by the app, supplied by
    nothing, and the failure was a startup crash with no explanation.
    """
    if not compose.exists():
        pytest.skip(f"{compose.name} not present")
    assert "PII_MASTER_KEY" in _compose_text(compose)


@pytest.mark.parametrize("compose", COMPOSE_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("secret", REQUIRED_SECRETS)
def test_secrets_have_no_fallback_default(compose, secret):
    """`${VAR:-something}` would let a deploy come up on a placeholder."""
    if not compose.exists():
        pytest.skip(f"{compose.name} not present")
    text = _compose_text(compose)
    if secret not in text:
        pytest.skip(f"{secret} not used by {compose.name}")
    assert f"${{{secret}:-" not in text, (
        f"{compose.name} gives {secret} a default value, so a deployment that forgot "
        "to set it starts anyway on a known secret"
    )
    assert f"${{{secret}:?" in text, f"{compose.name} should abort when {secret} is unset"


def test_the_env_example_ships_no_usable_secret():
    """A placeholder someone might mistake for a real value is worse than a blank."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for secret in REQUIRED_SECRETS:
        match = re.search(rf"^{secret}=(.*)$", text, re.MULTILINE)
        assert match, f"{secret} is not in .env.example"
        assert match.group(1).strip() == "", (
            f"{secret} carries a value in .env.example; leave it blank so it must be generated"
        )


def test_production_is_the_compose_environment():
    """It is what turns the missing-key check from a warning into a refusal."""
    for compose in COMPOSE_FILES:
        if compose.exists():
            assert "ENVIRONMENT: production" in _compose_text(compose), compose.name


# --- the guard those variables exist to arm -----------------------------------

def test_production_refuses_to_start_without_a_master_key(monkeypatch):
    from app.core.config import settings
    from app.services import crypto

    monkeypatch.setattr(settings, "pii_master_key", "")
    monkeypatch.setattr(settings, "environment", "production")
    with pytest.raises(RuntimeError) as excinfo:
        crypto.master_key()
    # The message has to carry the fix; a bare refusal at 2am is not help.
    assert "PII_MASTER_KEY" in str(excinfo.value)
    assert "base64" in str(excinfo.value)


def test_development_falls_back_loudly_rather_than_refusing(monkeypatch, caplog):
    """Local development runs with no setup — consistent with every other service."""
    from app.core.config import settings
    from app.services import crypto

    monkeypatch.setattr(settings, "pii_master_key", "")
    monkeypatch.setattr(settings, "environment", "development")
    with caplog.at_level("WARNING"):
        key = crypto.master_key()
    assert len(key) == 32
    assert any("PII_MASTER_KEY" in record.message for record in caplog.records), (
        "a derived key must be logged, or nobody learns their PII is only as strong "
        "as the JWT secret"
    )


def test_a_generated_key_is_accepted_as_is(monkeypatch):
    """The exact command the docs tell an operator to run."""
    from app.core.config import settings
    from app.services import crypto

    generated = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(settings, "pii_master_key", generated)
    monkeypatch.setattr(settings, "environment", "production")
    assert crypto.master_key() == base64.urlsafe_b64decode(generated)


def test_a_passphrase_is_stretched_rather_than_rejected(monkeypatch):
    """An operator who pastes a passphrase gets a working 32-byte key, not a crash."""
    from app.core.config import settings
    from app.services import crypto

    monkeypatch.setattr(settings, "pii_master_key", "correct horse battery staple")
    monkeypatch.setattr(settings, "environment", "production")
    assert len(crypto.master_key()) == 32


# --- what the key protects ----------------------------------------------------

def test_a_tenant_key_survives_a_wrap_and_unwrap(monkeypatch):
    from app.core.config import settings
    from app.services import crypto

    monkeypatch.setattr(settings, "pii_master_key", base64.urlsafe_b64encode(os.urandom(32)).decode())
    dek = crypto.generate_dek()
    assert crypto.unwrap_dek(crypto.wrap_dek(dek)) == dek


def test_a_changed_master_key_fails_loudly_rather_than_returning_garbage(monkeypatch):
    """The scenario behind "back the key up separately": a restore with the wrong key.

    AES-GCM authenticates, so this raises. It must never decrypt to nonsense that
    then gets written back over the real value.
    """
    from app.core.config import settings
    from app.services import crypto

    monkeypatch.setattr(settings, "pii_master_key", base64.urlsafe_b64encode(os.urandom(32)).decode())
    wrapped = crypto.wrap_dek(crypto.generate_dek())

    monkeypatch.setattr(settings, "pii_master_key", base64.urlsafe_b64encode(os.urandom(32)).decode())
    with pytest.raises(Exception):
        crypto.unwrap_dek(wrapped)


def test_a_tampered_ciphertext_is_rejected(monkeypatch):
    from app.core.config import settings
    from app.services import crypto

    monkeypatch.setattr(settings, "pii_master_key", base64.urlsafe_b64encode(os.urandom(32)).decode())
    key = crypto.generate_dek()
    blob = crypto.encrypt_with_key(key, "ABCDE1234F")
    assert crypto.decrypt_with_key(key, blob) == "ABCDE1234F"

    # Stored as `v1:<nonce>:<ciphertext>` — flip one bit inside the ciphertext.
    version, nonce_b64, ciphertext_b64 = blob.split(":", 2)
    raw = bytearray(base64.b64decode(ciphertext_b64))
    raw[-1] ^= 0x01
    tampered = f"{version}:{nonce_b64}:{base64.b64encode(bytes(raw)).decode()}"
    with pytest.raises(Exception):
        crypto.decrypt_with_key(key, tampered)


def test_a_ciphertext_from_a_future_version_is_refused():
    """A rollback must not decrypt data written by a newer format by accident."""
    from app.services import crypto

    key = crypto.generate_dek()
    blob = crypto.encrypt_with_key(key, "ABCDE1234F")
    _, nonce_b64, ciphertext_b64 = blob.split(":", 2)
    with pytest.raises(Exception):
        crypto.decrypt_with_key(key, f"v99:{nonce_b64}:{ciphertext_b64}")


# --- rate limiting ------------------------------------------------------------

def test_the_limiter_refuses_past_the_limit(monkeypatch):
    """The in-memory path, which is what a single-container deployment uses."""
    from app.core import rate_limit
    from app.core.exceptions import AppError

    rate_limit.reset()
    monkeypatch.setattr(rate_limit.settings, "redis_url", "")

    class _Request:
        client = type("C", (), {"host": "10.0.0.1"})()

    guard = rate_limit.rate_limiter("unit-test", limit=3)
    for _ in range(3):
        guard(_Request())
    with pytest.raises(AppError) as excinfo:
        guard(_Request())
    assert excinfo.value.status_code == 429


def test_the_limiter_separates_callers(monkeypatch):
    """One noisy client must not lock out everyone behind a different address."""
    from app.core import rate_limit

    rate_limit.reset()
    monkeypatch.setattr(rate_limit.settings, "redis_url", "")

    def request(ip):
        return type("R", (), {"client": type("C", (), {"host": ip})()})()

    guard = rate_limit.rate_limiter("unit-test-2", limit=2)
    guard(request("10.0.0.1"))
    guard(request("10.0.0.1"))
    guard(request("10.0.0.2"))  # a different caller still has their full budget


def test_the_limiter_warns_when_it_is_only_per_process(monkeypatch, caplog):
    """Otherwise a multi-worker deployment thinks it is protected and is not."""
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "redis_url", "")
    monkeypatch.setattr(rate_limit, "_warned_no_redis", False)
    with caplog.at_level("WARNING"):
        rate_limit._get_redis()
    assert any("per-process" in r.message for r in caplog.records)


def test_an_unreachable_redis_fails_open(monkeypatch):
    """A limiter that takes the product down when its cache blinks is worse than none."""
    from app.core import rate_limit

    rate_limit.reset()
    monkeypatch.setattr(rate_limit.settings, "redis_url", "redis://127.0.0.1:6399/0")
    monkeypatch.setattr(rate_limit, "_redis", None)
    monkeypatch.setattr(rate_limit, "_redis_failed", False)

    guard = rate_limit.rate_limiter("unit-test-3", limit=1)
    request = type("R", (), {"client": type("C", (), {"host": "10.0.0.9"})()})()
    guard(request)  # falls back rather than raising


def test_sign_in_is_rate_limited(client):
    """The endpoint that matters: an unlimited login is an offline password guess."""
    from app.core import rate_limit

    rate_limit.reset()
    codes = [
        client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
        ).status_code
        for _ in range(25)
    ]
    assert 429 in codes, "sign-in accepted 25 attempts without limiting"
    rate_limit.reset()
