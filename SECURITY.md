# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub:
**Security → Report a vulnerability** on this repository
(<https://github.com/codealisha99/ai-inference-layer/security/advisories/new>).
Do not open a public issue for security problems.

Include the affected port (Python, TypeScript, Go or Rust), the version or commit, and steps to
reproduce. You can expect an acknowledgement within a few days.

## Supported versions

Fixes land on `main`. The Python port is the reference implementation and receives security
hardening first.

## What the Python port already does

- Optional API key (`X-API-Key` or `Authorization: Bearer`), compared in constant time.
- Request body limit enforced while the body is read, so a false `Content-Length` cannot bypass it.
- Per-client token-bucket rate limiting with a bounded client table.
- Input, name, batch and model-count limits; bounded history per model.
- Security headers on every response, `Cache-Control: no-store` on API routes, and CORS closed
  unless `CORS_ORIGINS` is set.
- Request ids are sanitised before they are echoed or logged.
- Container runs as a non-root user.

## Deployment guidance

- Set `API_KEY` whenever the server is reachable beyond localhost, and terminate TLS in front of
  it (a reverse proxy or load balancer).
- Set `TRUST_PROXY=true` only when a proxy you control sets `X-Forwarded-For`; otherwise clients
  can spoof their rate-limit identity.
- Run one worker per SQLite database file and keep the file on a private volume.
- Rate limits are per process; enforce a global limit at the edge if you run several instances.
