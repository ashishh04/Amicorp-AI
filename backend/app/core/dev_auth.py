"""Local sign-in for the portal and the tests (ENVIRONMENT local or test only).

A laptop has no Entra tenant. The API signs short-lived tokens for the local users with a key it creates
at start-up, and validates them the same way as Entra tokens: RS256, issuer, audience, lifetime, roles.
The router that issues them is mounted only in local and test, and the key never leaves the process, so
a restart invalidates every local token.
"""
import time
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

DEV_ISSUER = "https://amc.local/dev-sign-in"
DEV_AUDIENCE = "amc-platform-api-local"
DEV_KID = "amc-local-dev"
TOKEN_TTL_SECONDS = 8 * 3600


class DevSigner:
    def __init__(self) -> None:
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self._key.public_key()

    def issue(self, user_id: str, roles: list[str]) -> str:
        now = int(time.time())
        claims = {
            "iss": DEV_ISSUER, "aud": DEV_AUDIENCE, "tid": "local", "oid": user_id, "sub": user_id,
            "azp": "amc-portal-local", "scp": "access_as_user", "roles": roles,
            "iat": now, "nbf": now, "exp": now + TOKEN_TTL_SECONDS, "uti": uuid.uuid4().hex,
        }
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": DEV_KID})
