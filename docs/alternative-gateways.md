# Alternative API Gateway Tools

The gateway configuration is designed to be replaceable.
All routing logic lives in `traefik/config/routes.yml`.
To switch tools, only the gateway layer changes — microservices are untouched.

---

## Current: Traefik v3

- File: `traefik/traefik.yml` + `traefik/config/routes.yml`
- Start: `docker compose up -d`
- Dashboard: http://localhost:8090/dashboard/

---

## Option 2: Kong Gateway

**When to use:** Production, advanced plugins, rate limiting per user tier.

Equivalent Kong config for the experience-service route:

```yaml
# kong/kong.yml
services:
  - name: experience-service
    url: http://experience-service:8002
    routes:
      - name: experience-routes
        paths:
          - /api/v1/experiences
          - /api/v1/stays
          - /api/v1/dining
          - /api/v1/spa
    plugins:
      - name: jwt
        config:
          secret_is_base64: false
          key_claim_name: azp
      - name: cors
        config:
          origins: ["http://localhost:3000"]
          methods: [GET, POST, PATCH, DELETE, OPTIONS]
          headers: [Authorization, Content-Type]
      - name: rate-limiting
        config:
          minute: 100
          policy: local
```

Start Kong:
```bash
docker run -d --name kong \
  -e KONG_DATABASE=off \
  -e KONG_DECLARATIVE_CONFIG=/kong/kong.yml \
  -v ./kong:/kong \
  -p 80:8000 -p 8001:8001 \
  kong:latest
```

---

## Option 3: KrakenD

**When to use:** High throughput, zero latency overhead, config-driven.

```json
{
  "version": 3,
  "endpoints": [
    {
      "endpoint": "/api/v1/experiences",
      "backend": [{ "url_pattern": "/api/v1/experiences", "host": ["http://experience-service:8002"] }],
      "extra_config": {
        "auth/validator": {
          "alg": "RS256",
          "jwk_url": "http://keycloak:8080/realms/experience/protocol/openid-connect/certs",
          "disable_jwk_security": true
        }
      }
    }
  ]
}
```

---

## Option 4: nginx (simple reverse proxy, no JWT validation)

**When to use:** Minimal setup, JWT validation handled by each service.

```nginx
# nginx/nginx.conf
upstream experience { server experience-service:8002; }
upstream booking    { server booking-service:8003; }

server {
    listen 80;

    location /api/v1/experiences { proxy_pass http://experience; }
    location /api/v1/bookings    { proxy_pass http://booking; }
}
```

---

## Option 5: Azure API Management (cloud production)

**When to use:** Azure deployment, enterprise features, monitoring.

- Import OpenAPI specs from each service
- Configure JWT validation policy pointing to Keycloak or Entra ID
- Only `KEYCLOAK_REALM_URL` changes per environment
- No microservice code changes needed

---

## Migration Steps (any tool)

1. Update `services` section with new upstream addresses
2. Map the middleware (CORS, auth, rate limit) to the new tool's equivalent
3. Keep `X-User-ID`, `X-User-Email`, `X-User-Roles` headers — microservices depend on these
4. Test with: `curl -H "Authorization: Bearer <token>" http://localhost/api/v1/experiences`
