"""Bearer-token verification for tokens issued by WorkOS AuthKit.

This server can run as an OAuth 2.1 *resource server*: WorkOS AuthKit acts as
the authorization server and handles the actual OAuth dance with clients
(Dynamic Client Registration, user login/consent, token issuance/refresh).
All this module does is check that a bearer token presented on an incoming
request was genuinely issued by *our* AuthKit project, for *this* resource
server, and hasn't expired - it never talks to WorkOS on the write path and
never sees a password or client secret.

Wired in from server.py only when WORKOS_AUTHKIT_DOMAIN and MCP_RESOURCE_URL
are set; local stdio use is unaffected.
"""

from __future__ import annotations

import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

# WorkOS AuthKit signs access tokens with RS256. Pinning this explicitly
# (rather than trusting whatever `alg` the token claims) rules out
# algorithm-confusion attacks against the verifier.
ALGORITHMS = ["RS256"]


class WorkOSTokenVerifier(TokenVerifier):
    """Validates JWT access tokens issued by a WorkOS AuthKit project.

    The signature is checked against AuthKit's published JWKS. The issuer
    and audience (the RFC 8707 resource indicator) are checked against this
    deployment's own configuration, so a token minted for some *other*
    resource server can't be replayed against this one.
    """

    def __init__(self, authkit_domain: str, resource_url: str) -> None:
        self.authkit_domain = authkit_domain.rstrip("/")
        self.resource_url = resource_url
        self._jwks_client = jwt.PyJWKClient(
            f"{self.authkit_domain}/oauth2/jwks", cache_keys=True
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALGORITHMS,
                issuer=self.authkit_domain,
                audience=self.resource_url,
                options={"require": ["exp", "iat"]},
            )
        except jwt.PyJWTError:
            return None
        except Exception:
            # JWKS fetch failures, malformed tokens, unexpected key types,
            # etc. Fail closed - an unverifiable token is not a valid one.
            return None

        scope_claim = claims.get("scope") or claims.get("scp") or ""
        scopes = scope_claim.split() if isinstance(scope_claim, str) else list(scope_claim)

        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id") or claims.get("sub") or "unknown"),
            scopes=scopes,
            expires_at=claims.get("exp"),
            resource=self.resource_url,
            subject=claims.get("sub"),
            claims=claims,
        )
