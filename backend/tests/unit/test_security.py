"""Token validation against locally signed tokens, shaped like Entra ID v2 access tokens."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings
from app.core.errors import Forbidden, Unauthorized
from app.core.principal import Role
from app.core.security import TokenValidator

TENANT = "11111111-1111-1111-1111-111111111111"
API_CLIENT_ID = "22222222-2222-2222-2222-222222222222"
PORTAL_SPA = "33333333-3333-3333-3333-333333333333"
N8N_CLIENT = "44444444-4444-4444-4444-444444444444"
DEV_TOKEN = "dev-token-for-unit-tests-0123456789abcdef"

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()


@pytest.fixture
def validator(monkeypatch) -> TokenValidator:
    for name in ("ENVIRONMENT", "AUTOMATION_DEV_TOKEN", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(
        _env_file=None, environment="test", database_url="postgresql+psycopg://u@127.0.0.1/db",
        entra_tenant_id=TENANT, entra_api_client_id=API_CLIENT_ID,
        entra_allowed_client_ids=[PORTAL_SPA, N8N_CLIENT], automation_dev_token=DEV_TOKEN,
    )
    return TokenValidator(settings)


def token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": API_CLIENT_ID,
        "tid": TENANT,
        "oid": "55555555-5555-5555-5555-555555555555",
        "azp": PORTAL_SPA,
        "scp": "access_as_user",
        "roles": ["Checker"],
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
        "uti": "token-id",
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256")


def test_accepts_a_user_token_whose_audience_is_the_client_id(validator):
    principal = validator.decode(token(), PUBLIC_KEY)
    assert principal.kind == "user"
    assert principal.roles == {Role.CHECKER}
    assert principal.token_id == "token-id"


def test_rejects_the_api_uri_as_audience(validator):
    # Blueprint finding F1: v2 tokens carry the client ID in `aud`, never the api:// URI.
    with pytest.raises(Unauthorized):
        validator.decode(token(aud="api://amc-platform-api"), PUBLIC_KEY)


def test_accepts_an_automation_app_token(validator):
    principal = validator.decode(token(azp=N8N_CLIENT, scp=None, idtyp="app", roles=["Automation"]), PUBLIC_KEY)
    assert principal.kind == "service"
    assert principal.roles == {Role.AUTOMATION}
    assert principal.subject == N8N_CLIENT


def test_refuses_an_app_token_without_the_automation_role(validator):
    with pytest.raises(Forbidden):
        validator.decode(token(azp=N8N_CLIENT, scp=None, idtyp="app", roles=[]), PUBLIC_KEY)


def test_a_user_token_never_grants_automation(validator):
    principal = validator.decode(token(roles=["Automation", "Maker"]), PUBLIC_KEY)
    assert principal.roles == {Role.MAKER}


def test_rejects_another_tenant(validator):
    with pytest.raises(Unauthorized):
        validator.decode(token(tid="99999999-9999-9999-9999-999999999999"), PUBLIC_KEY)


def test_rejects_a_client_that_is_not_allowed(validator):
    with pytest.raises(Unauthorized):
        validator.decode(token(azp="66666666-6666-6666-6666-666666666666"), PUBLIC_KEY)


def test_rejects_an_expired_token(validator):
    past = int(time.time()) - 7200
    with pytest.raises(Unauthorized):
        validator.decode(token(iat=past, nbf=past, exp=past + 600), PUBLIC_KEY)


def test_rejects_a_symmetric_algorithm(validator):
    forged = jwt.encode({"aud": API_CLIENT_ID}, "shared-secret-shared-secret-shared-secret", algorithm="HS256")
    with pytest.raises(Unauthorized):
        validator.decode(forged, PUBLIC_KEY)


@pytest.mark.anyio
async def test_dev_token_gives_the_automation_role_in_test(validator):
    principal = await validator.authenticate(DEV_TOKEN)
    assert principal.kind == "service"
    assert principal.roles == {Role.AUTOMATION}
