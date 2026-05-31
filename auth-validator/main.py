"""
auth-validator — JWT validation sidecar for Traefik forwardAuth
───────────────────────────────────────────────────────────────
Traefik calls POST /validate before forwarding any protected request.
This service verifies the Keycloak JWT and returns user identity headers.

Flow:
  Client → Traefik → POST /validate (this service)
                          ↓
                     Verify JWT via Keycloak JWKS
                          ↓
                     Return 200 + X-User-* headers  →  Traefik forwards to service
                     Return 401                      →  Traefik returns 401 to client

Environment:
  KEYCLOAK_REALM_URL  : Keycloak realm base URL
  PORT                : Port this service listens on (default 9000)
"""

import os
import time
import logging
from typing import Optional, Dict, Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from jose import jwt, JWTError, ExpiredSignatureError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

KEYCLOAK_REALM_URL = os.getenv("KEYCLOAK_REALM_URL", "http://localhost:8080/realms/experience")
# Issuer is what Keycloak puts in the JWT iss claim — always uses the public hostname
# JWKS URL uses the internal Docker hostname to fetch keys from within the container network
KEYCLOAK_ISSUER_URL = os.getenv("KEYCLOAK_ISSUER_URL", "http://localhost:8080/realms/experience")
JWKS_URL = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/certs"
ALGORITHMS = ["RS256"]
JWKS_CACHE_TTL = 300  # 5 minutes

_jwks_cache: Optional[Dict] = None
_jwks_fetched_at: float = 0.0

app = FastAPI(title="Experience Auth Validator", docs_url=None, redoc_url=None)


async def fetch_jwks() -> Dict:
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < JWKS_CACHE_TTL:
        return _jwks_cache
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(JWKS_URL)
        r.raise_for_status()
        _jwks_cache = r.json()
        _jwks_fetched_at = now
        logger.info("JWKS refreshed from %s", JWKS_URL)
        return _jwks_cache


def extract_roles(payload: Dict[str, Any]) -> list:
    # Custom realm mapper puts roles directly in 'roles' claim
    if "roles" in payload and isinstance(payload["roles"], list):
        return payload["roles"]
    # Fallback: standard Keycloak realm_access format
    return payload.get("realm_access", {}).get("roles", [])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-validator"}


@app.get("/validate")
@app.post("/validate")
async def validate(request: Request):
    """
    Traefik forwardAuth endpoint.
    Returns 200 + user headers on success, 401 on failure.
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return Response(
            content="Missing or invalid Authorization header",
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:]

    try:
        jwks = await fetch_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=ALGORITHMS,
            issuer=KEYCLOAK_ISSUER_URL,
            options={"verify_aud": False},
        )
    except ExpiredSignatureError:
        return Response(content="Token expired", status_code=401,
                        headers={"WWW-Authenticate": "Bearer"})
    except JWTError as e:
        logger.warning("JWT verification failed: %s", e)
        return Response(content="Invalid token", status_code=401,
                        headers={"WWW-Authenticate": "Bearer"})
    except Exception as e:
        logger.error("Auth validator error: %s", e)
        return Response(content="Authentication service error", status_code=503)

    roles = extract_roles(payload)

    # Return 200 with user identity headers
    # Traefik will forward these to the upstream microservice
    return Response(
        status_code=200,
        headers={
            "X-User-ID":    payload.get("sub", ""),
            "X-User-Email": payload.get("email", ""),
            "X-User-Roles": ",".join(roles),
            "X-User-Name":  payload.get("name", ""),
        },
    )
