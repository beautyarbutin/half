# Safe Deploy Guide

## Why this exists

This server is resource-constrained. Rebuilding HALF too aggressively on the host can make the machine unresponsive and may cut off SSH access during deployment.

Agents must treat deployment as a safety-critical operation, not a routine `docker compose up --build -d`.

## Mandatory deploy rules

1. Do not run `docker compose up --build -d` blindly on the server.
2. Prefer a staged deploy:
   - start Docker explicitly if needed
   - build `backend` first
   - build `frontend` second
   - run `docker compose up -d`
3. Keep builds serial, not parallel.
4. Do not re-enable Docker autostart unless the user explicitly asks for it.
5. Before a rebuild, check available memory and disk.
6. If memory is tight, stop unrelated containers or services before building.
7. If the change does not require a rebuild, prefer restarting only the affected service.

## Minimum pre-deploy checks

Run these before rebuilding on the server:

```bash
free -h
df -h
docker info
docker compose ps
```

If memory is low or the machine is already under pressure, stop and tell the user.

## Preferred deploy sequence

From `src/`:

```bash
docker compose build backend
docker compose build frontend
docker compose up -d
docker compose ps
```

## Extra caution rules

- Avoid rebuilding multiple stacks at once on this host.
- Avoid enabling unrelated auto-start services during deployment.
- If Docker was manually disabled for stability, keep it disabled after deployment unless the user asks otherwise.
- After deploy, verify both:
  - backend health
  - frontend HTTP response

## Verification examples

```bash
curl -sS http://127.0.0.1:8000/
curl -I http://127.0.0.1:3000
docker compose ps
```

## When documenting deploy actions

If an agent deploys HALF, it should record:

- what was built
- whether Docker autostart changed
- what verification passed
- any remaining operational risk
