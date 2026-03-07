# Stage 3 Report — DevOps Early

## Scope
- Dockerized the FastAPI backend with Postgres and an NGINX HTTPS proxy for the test environment.
- Added GitHub Actions CI that installs dependencies, runs static checks (`python -m compileall`), and validates the Docker Compose configuration.

## Completed
- `backend/Dockerfile` builds the minimal Python image and exposes the app via Uvicorn.
- `docker-compose.yml` wires Postgres, backend, and `nginx` serving TLS on port 8443 using the seeded certificate pair in `certs/` plus `nginx/nginx.conf` for reverse proxying.
- Root `README.md` now documents how to bootstrap the compose stack and trust the self-signed cert for HTTPS tests.
- `.github/workflows/ci.yml` implements the Stage 3 pipeline, confirming environment health and Docker Compose config.

## Tests
- `python -m compileall backend/app`
- `docker compose config` *(not run locally—`docker` binary unavailable in this sandbox; the workflow executes it on GitHub runners).* 

## Next
- Stage 4 (Designer UI) will integrate the split pages with the `/api` endpoints and craft the Canvas/SVG visualizer.
