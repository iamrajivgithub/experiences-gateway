# experiences-gateway

API Gateway for the Experience Platform.
Single entry point for all microservice traffic — handles routing, JWT validation, CORS, and rate limiting.

Current implementation: **Traefik v3** (replaceable — see docs/alternative-gateways.md)

---

## Purpose

The API Gateway sits in front of all microservices and is responsible for:

- Routing incoming requests to the correct microservice
- JWT validation — verifies Keycloak tokens once at the edge
- Forwarding user identity — passes X-User-ID, X-User-Email, X-User-Roles headers to services
- CORS — handles cross-origin headers centrally
- Rate limiting — protects services from abuse
- Security headers — adds standard HTTP security headers to all responses

Microservices trust the gateway — they do not re-validate tokens.
They simply read the X-User-* headers to know who the caller is.

---

## Architecture

```
Client
  |
  v
Traefik Gateway :80
  |
  |-- /api/v1/experiences  -->  experience-service    :8002
  |-- /api/v1/bookings     -->  booking-service       :8003
  |-- /api/v1/users        -->  user-service          :8004
  |-- /api/v1/reviews      -->  review-service        :8005
  |-- /api/v1/search       -->  search-service        :8006
  |-- /api/v1/media        -->  media-service         :8007
  `-- /api/v1/notifications --> notification-service  :8008

For protected routes, Traefik calls auth-validator first:

  Client --> Traefik --> auth-validator :9000 (verify JWT via Keycloak JWKS)
                              |
                         200 + X-User-* headers
                              |
                         Traefik --> microservice (with headers attached)
```

---

## Repository Structure

```
experiences-gateway/
|-- docker-compose.yml              <- Traefik + auth-validator containers
|-- .env.example                    <- configuration template
|-- .gitignore
|-- README.md
|-- traefik/
|   |-- traefik.yml                 <- static config (ports, dashboard, logging)
|   `-- config/
|       `-- routes.yml              <- dynamic config (routes, middleware, services)
|-- auth-validator/
|   |-- main.py                     <- FastAPI JWT validation sidecar
|   |-- requirements.txt
|   `-- Dockerfile
`-- docs/
    `-- alternative-gateways.md    <- Kong, KrakenD, nginx, Azure APIM equivalents
```

---

## Pre-Requisites

- Docker Desktop running
- Keycloak running (see experiences-auth repository)
- Microservices running (see experiences-services repository)

---

## Setup and Start

### Step 1 - Clone the Repository

```powershell
git clone https://github.com/iamrajivgithub/experiences-gateway
cd experiences-gateway
```

### Step 2 - Create .env File

```powershell
copy .env.example .env
```

Edit .env if Keycloak is running on a different URL.

### Step 3 - Start the Gateway

```powershell
docker compose --env-file .env up -d
```

### Step 4 - Verify

```powershell
docker compose ps
```

Both experience_api_gateway and experience_auth_validator should show healthy.

- Gateway   : http://localhost:80
- Dashboard : http://localhost:8090/dashboard/

---

## Request Flow

### Public route (no token needed)

```
GET http://localhost/api/v1/experiences
  > Traefik applies CORS + security headers + rate limit
  > Forwards to experience-service:8002
```

### Protected route (token required)

```
GET http://localhost/api/v1/bookings
Authorization: Bearer eyJhbGc...
  > Traefik calls auth-validator:9000/validate
  > auth-validator verifies JWT via Keycloak JWKS (cached 5 min)
  > Returns 200 + headers:
      X-User-ID: 6b0c9008-2941-450c-98f0-ec79ba269ea3
      X-User-Email: member@experience.com
      X-User-Roles: member,guest
  > Traefik forwards to booking-service:8003 with X-User-* headers
```

### Rejected request (invalid token)

```
GET http://localhost/api/v1/bookings
Authorization: Bearer invalid-token
  > auth-validator returns 401
  > Traefik returns 401 to client (booking-service never receives it)
```

---

## Routes Summary

| Path Prefix | Service | Auth Required |
|---|---|---|
| /api/v1/experiences | experience-service :8002 | No |
| /api/v1/stays | experience-service :8002 | No |
| /api/v1/dining | experience-service :8002 | No |
| /api/v1/spa | experience-service :8002 | No |
| /api/v1/bookings | booking-service :8003 | Yes |
| /api/v1/payments | booking-service :8003 | Yes |
| /api/v1/users | user-service :8004 | Yes |
| /api/v1/reviews | review-service :8005 | No |
| /api/v1/search | search-service :8006 | No |
| /api/v1/media | media-service :8007 | Yes |
| /api/v1/notifications | notification-service :8008 | Yes |

---

## Headers Passed to Microservices

| Header | Value | Source |
|---|---|---|
| X-User-ID | Keycloak user UUID | JWT sub claim |
| X-User-Email | User email | JWT email claim |
| X-User-Roles | Comma-separated roles | JWT roles claim |
| X-User-Name | Full name | JWT name claim |
| X-Gateway | experiences-gateway | Static |

---

## Rate Limits

| Route Type | Requests/second | Burst | Limited by |
|---|---|---|---|
| Public routes | 100 | 50 | IP address |
| Authenticated routes | 300 | 100 | X-User-ID |

---

## Management Commands

```powershell
# Start gateway
docker compose --env-file .env up -d

# Stop gateway
docker compose down

# View Traefik logs
docker compose logs -f traefik

# View auth-validator logs
docker compose logs -f auth-validator

# Check status
docker compose ps

# Reload routes without restart
# Edit traefik/config/routes.yml and save — changes apply instantly (file is watched)
```

---

## Adding a New Microservice

Edit traefik/config/routes.yml — no restart needed:

```yaml
# 1. Add a router
routers:
  my-new-service:
    rule: "PathPrefix(`/api/v1/my-endpoint`)"
    entryPoints: [web]
    middlewares: [cors, jwt-auth, request-headers, rate-limit-auth]
    service: my-new-service

# 2. Add a service
services:
  my-new-service:
    loadBalancer:
      servers:
        - url: "http://my-new-service:8009"
      healthCheck:
        path: /health
        interval: 10s
```

---

## Replacing Traefik with Another Tool

All routing logic is in traefik/config/routes.yml.
See docs/alternative-gateways.md for equivalent configs for:

- Kong Gateway
- KrakenD
- nginx
- Azure API Management

Migration checklist:
- Translate routes from routes.yml to the new tool's format
- Keep the X-User-* header names (microservices depend on these)
- Point JWT validation to the same Keycloak JWKS endpoint
- No microservice code changes needed

---

## Azure Migration

- Replace Traefik with Azure API Management (fully managed)
- Or deploy Traefik on Azure Container Apps
- Update KEYCLOAK_REALM_URL in .env to the production Keycloak URL
- Update service URLs in routes.yml to Azure-hosted endpoints
- No application code changes needed

---

## Related Repositories

| Repository | Purpose |
|---|---|
| experiences-auth | Keycloak identity provider (https://github.com/iamrajivgithub/experiences-auth) |
| experiences-lib-auth | Shared JWT library (https://github.com/iamrajivgithub/experiences-lib-auth) |
| experiences-services | All microservices (https://github.com/iamrajivgithub/experiences-services) |
| experiences-data | Database stack (https://github.com/iamrajivgithub/experiences-data) |
