"""Authentication: Entra ID access tokens, plus a static dev token for n8n on a laptop.

Rules (LLD, Authentication and authorisation; blueprint section 9, token rules):
- RS256 only, keys from the tenant's JWKS; issuer, tenant, audience, lifetime and calling app checked.
- With token version 2 the audience is the API's client ID (a GUID). Checking the api:// URI instead
  would reject every real token (blueprint finding F1).
- App-only tokens must carry the Automation role; a user token can never grant it.
- The dev token is accepted only when ENVIRONMENT is local or test; Settings refuses it elsewhere.
- Local sign-in tokens (app/core/dev_auth.py) are checked like Entra tokens, and only in local and test.
"""
import hmac

import jwt
import structlog
from fastapi import Request
from jwt import PyJWKClient
from starlette.concurrency import run_in_threadpool

from app.core.config import LOCAL_ENVIRONMENTS, Settings
from app.core.dev_auth import DEV_AUDIENCE, DEV_ISSUER, DEV_KID, DevSigner
from app.core.errors import Forbidden, Unauthorized
from app.core.principal import Principal, Role

log = structlog.get_logger()

_KNOWN_ROLES = {r.value: r for r in Role}
_DEV_SUBJECT = "automation-dev"


class TokenValidator:
    def __init__(
        self, settings: Settings, jwks_client: PyJWKClient | None = None, dev_signer: DevSigner | None = None
    ) -> None:
        local = settings.environment in LOCAL_ENVIRONMENTS
        self._dev_token: bytes | None = None
        if settings.automation_dev_token is not None and local:
            self._dev_token = settings.automation_dev_token.get_secret_value().encode()
        self._dev_signer = dev_signer if local else None

        self._tenant = settings.entra_tenant_id
        self._audience = settings.entra_api_client_id
        self._allowed_clients = frozenset(settings.entra_allowed_client_ids)
        self._issuer = f"https://login.microsoftonline.com/{self._tenant}/v2.0" if self._tenant else None
        self._jwks = jwks_client
        if self._jwks is None and self._tenant:
            self._jwks = PyJWKClient(
                f"https://login.microsoftonline.com/{self._tenant}/discovery/v2.0/keys",
                cache_keys=True,
                lifespan=3600,
            )

    async def authenticate(self, token: str) -> Principal:
        if self._dev_token is not None and hmac.compare_digest(token.encode(), self._dev_token):
            return Principal(subject=_DEV_SUBJECT, kind="service", roles=frozenset({Role.AUTOMATION}))
        if self._dev_signer is not None and _key_id(token) == DEV_KID:
            return self._decode_local(token, self._dev_signer)
        if self._jwks is None or not self._audience:
            raise Unauthorized("Token not accepted")
        try:
            # The JWKS lookup can hit the network on a key rotation, so keep it off the event loop.
            signing_key = await run_in_threadpool(self._jwks.get_signing_key_from_jwt, token)
        except jwt.PyJWTError as exc:
            log.info("auth.failed", reason="signing_key")
            raise Unauthorized("Invalid token") from exc
        return self.decode(token, signing_key.key)

    def decode(self, token: str, key: object) -> Principal:
        try:
            claims = jwt.decode(
                token,
                key,  # type: ignore[arg-type]
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                leeway=60,
                options={"require": ["exp", "nbf", "iat", "aud", "iss", "tid", "oid"]},
            )
        except jwt.PyJWTError as exc:
            log.info("auth.failed", reason=type(exc).__name__)
            raise Unauthorized("Invalid token") from exc

        if claims.get("tid") != self._tenant:
            log.info("auth.failed", reason="tenant")
            raise Unauthorized("Invalid token")
        client_id = claims.get("azp")
        if self._allowed_clients and client_id not in self._allowed_clients:
            log.info("auth.failed", reason="client_not_allowed")
            raise Unauthorized("Client not allowed")

        roles = {_KNOWN_ROLES[r] for r in claims.get("roles", []) if r in _KNOWN_ROLES}
        is_app_token = claims.get("idtyp") == "app" or "scp" not in claims
        if is_app_token:
            if Role.AUTOMATION not in roles:
                raise Forbidden("Application token without the Automation role")
            return Principal(
                subject=str(client_id or claims["oid"]), kind="service",
                roles=frozenset({Role.AUTOMATION}), token_id=claims.get("uti"),
            )
        roles.discard(Role.AUTOMATION)
        return Principal(subject=str(claims["oid"]), kind="user", roles=frozenset(roles), token_id=claims.get("uti"))


    @staticmethod
    def _decode_local(token: str, signer: DevSigner) -> Principal:
        try:
            claims = jwt.decode(
                token, signer.public_key, algorithms=["RS256"], audience=DEV_AUDIENCE, issuer=DEV_ISSUER,
                options={"require": ["exp", "nbf", "iat", "aud", "iss", "oid"]},
            )
        except jwt.PyJWTError as exc:
            log.info("auth.failed", reason=f"local:{type(exc).__name__}")
            raise Unauthorized("Invalid token") from exc
        roles = {_KNOWN_ROLES[r] for r in claims.get("roles", []) if r in _KNOWN_ROLES} - {Role.AUTOMATION}
        return Principal(subject=str(claims["oid"]), kind="user", roles=frozenset(roles), token_id=claims.get("uti"))


def _key_id(token: str) -> str | None:
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        return None
    return kid if isinstance(kid, str) else None


async def current_principal(request: Request) -> Principal:
    """FastAPI dependency: the authenticated caller, or 401."""
    cached: Principal | None = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    validator: TokenValidator = request.app.state.token_validator
    principal = await validator.authenticate(token.strip())
    request.state.principal = principal
    structlog.contextvars.bind_contextvars(actor=principal.log_actor)
    return principal
