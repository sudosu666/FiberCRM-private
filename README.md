# FiberOps CRM — DevOps Stage

## Stage 3 (DevOps Early)
1. `docker compose up --build` spins up Postgres, FastAPI backend, and an NGINX reverse proxy that terminates TLS on port `8443` using the self-signed cert in `certs/local.crt`. The backend exposes `/api` endpoints described in Stage 2 for frontend consumption.
2. Environment variables mirror `backend/.env.example`; the compose file overrides `DATABASE_URL` to point at the `db` service and reuses the demo `JWT_SECRET`.
3. GitHub Actions (`.github/workflows/ci.yml`) installs dependencies, runs `python -m compileall backend/app`, and validates the Docker Compose configuration.

### HTTPS testing
The `nginx` service listens on port `8443` and uses the bundled cert/key pair so you can hit `https://localhost:8443/api/tasks`. Trust `certs/local.crt` in your OS/browser if needed. Use `curl --insecure` during early stages.

### Next steps
- Stage 4 will plug the split UI into the `/api` surface and add the Canvas/SVG visualizer.
- Stage 5 will layer real-time WebSocket events on top of `/api` so the dispatcher/brigade views receive live task/brigade status, timeline, and chat updates.
