# Python Agents Node Backend

An Express REST API that starts the existing CrewAI Web or Mobile workflow in a separate Python process. Python remains responsible for agent execution and generated files; the Flask dashboard, CLI, and deterministic demo mode are unchanged.

## Architecture

`POST /api/build` validates the request and creates an in-memory job. The job manager runs at most `MAX_CONCURRENT_BUILDS` Python jobs and keeps additional work in a bounded queue. It invokes `agent_api_runner.py` with `child_process.spawn`, `shell: false`, and JSON on stdin. The Python bridge runs `AutonomousSupervisor.run()` for Web or `MobileWorkflow.build_crew(...).kickoff()` for Mobile. Both receive tools scoped to `output/<platform>-<job-uuid>/`.

The bridge writes one machine-readable JSON object to stdout. Progress and diagnostics use stderr; the Node process stores only a bounded, sanitized tail in the job record. Jobs and logs live in memory and are lost when Node restarts. This initial version does not persist jobs or coordinate concurrency across multiple Node instances.

The Web supervisor's local URL is process-owned and does not remain available once its Python child exits. The API therefore omits loopback URLs. A non-loopback URL is returned only when the configured deployment path supplies one. Mobile builds do not return a URL.

## Prerequisites

- Node.js 18 or newer and npm.
- A Python version supported by the installed CrewAI dependencies.
- The repository's Python dependencies and valid LLM provider settings for live agent runs.

## Setup

From the repository root, create and populate the existing project's virtual environment.

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item node-backend\.env.example node-backend\.env
Set-Location node-backend
npm install
```

Linux or macOS:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp node-backend/.env.example node-backend/.env
cd node-backend
npm install
```

The Python provider continues to load its configuration from the repository-root `.env`. Keep that file unchanged; do not copy secrets into `node-backend/.env`. The backend-local environment file is for Node settings only and is ignored by Git. `TARGET_URL` and `TARGET_MODEL` are not changed by this integration.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `3000` | Express listen port |
| `PYTHON_EXECUTABLE` | `.venv` Python, then `python`/`python3` on PATH | Explicit Python executable override |
| `MAX_CONCURRENT_BUILDS` | `1` | Simultaneous Python agent runs; capped at 8 |
| `MAX_QUEUED_BUILDS` | `20` | Maximum waiting jobs; excess requests receive HTTP 503 |
| `BUILD_TIMEOUT_MS` | `1800000` | Per-build timeout in milliseconds; capped at one hour |

Node reads `node-backend/.env` and the current process environment. Python independently loads the existing root `.env` through `python-dotenv`.

## Run

From `node-backend/`:

```sh
npm start
```

For automatic restart during backend development, use `npm run dev`. The backend listens on the configured port, default `http://localhost:3000`.

## API

All responses use `{ "success": true, "data": ... }` or `{ "success": false, "error": ... }`.

### Health

```sh
curl http://localhost:3000/api/health
```

Example:

```json
{
  "success": true,
  "data": {
    "status": "ok",
    "runtime": {
      "nodeVersion": "v22.0.0",
      "port": 3000,
      "pythonExecutableSource": ".venv",
      "pythonExecutableConfigured": true,
      "projectEnvFilePresent": true,
      "maxConcurrentBuilds": 1,
      "activeBuilds": 0,
      "queuedBuilds": 0
    }
  }
}
```

The health response exposes configuration status only, not environment values or credentials.

### Start a build

```sh
curl -X POST http://localhost:3000/api/build \
  -H "Content-Type: application/json" \
  -d '{"platform":"web","requirement":"Build a calculator website with addition, subtraction, multiplication, and division"}'
```

Set `platform` to `web` or `mobile`; `requirement` must be non-empty and no longer than 8,000 characters. A valid request returns HTTP 202:

```json
{
  "success": true,
  "data": {
    "jobId": "38f8e128-8997-4a48-a3e7-7ad0b43a8389",
    "status": "queued",
    "statusUrl": "/api/jobs/38f8e128-8997-4a48-a3e7-7ad0b43a8389"
  }
}
```

The initial status may already be `running` if a worker slot was free when the request was accepted.

### Check a job

```sh
curl http://localhost:3000/api/jobs/38f8e128-8997-4a48-a3e7-7ad0b43a8389
```

Successful job example:

```json
{
  "success": true,
  "data": {
    "id": "38f8e128-8997-4a48-a3e7-7ad0b43a8389",
    "projectId": "web-38f8e128-8997-4a48-a3e7-7ad0b43a8389",
    "platform": "web",
    "status": "succeeded",
    "createdAt": "2026-10-10T08:00:00.000Z",
    "startedAt": "2026-10-10T08:00:01.000Z",
    "completedAt": "2026-10-10T08:02:00.000Z",
    "progress": { "stage": "complete", "percent": 100, "message": "Web build completed." },
    "recentLogs": [],
    "projectPath": "<repository>/output/web-38f8e128-8997-4a48-a3e7-7ad0b43a8389",
    "result": {
      "status": "succeeded",
      "generatedFiles": ["index.html", "styles.css", "script.js"],
      "finalUrl": null,
      "message": "Web build completed.",
      "error": null
    },
    "error": null
  }
}
```

Failed job example:

```json
{
  "success": true,
  "data": {
    "id": "38f8e128-8997-4a48-a3e7-7ad0b43a8389",
    "projectId": "mobile-38f8e128-8997-4a48-a3e7-7ad0b43a8389",
    "platform": "mobile",
    "status": "failed",
    "projectPath": "<repository>/output/mobile-38f8e128-8997-4a48-a3e7-7ad0b43a8389",
    "result": { "status": "failed", "generatedFiles": [], "finalUrl": null },
    "error": { "type": "MobileQAFailed", "message": "Mobile QA task reported failure." }
  }
}
```

An unknown job returns HTTP 404. Invalid JSON and build input return HTTP 400; a full queue returns HTTP 503. Use these requests in Postman with the same URL, JSON body, and `Content-Type: application/json` header.

## Tests

From `node-backend/`, run `npm test`. From the repository root, run the bridge tests with:

```sh
python -m pytest tests/test_agent_api_runner.py -q
```

These tests mock agent execution and the Python process boundary. They do not make LLM calls. No real Web or Mobile generation is claimed by the automated tests.

## Troubleshooting and limitations

- If Python cannot start, set `PYTHON_EXECUTABLE` to the full path of the project interpreter. Health reports which selection source is active but does not launch a build to probe it.
- If the Python process starts but agent configuration fails, check the existing repository-root `.env` and the provider's required LLM configuration. The API returns a sanitized failed job; it does not reveal credentials.
- Install Python dependencies in the selected interpreter with `python -m pip install -r requirements.txt`.
- Mobile tasks are executed through `MobileWorkflow.build_crew(...).kickoff()`, not the deterministic demo runner or the state-only `MobileWorkflow.run()` method.
- Jobs, progress, and logs are in-memory only. Restarting Node loses the job records; this implementation is intended for one backend instance.
- Agent generation still depends on configured external LLM access and may take several minutes. Timeouts and concurrency limits are configurable.
- The Python process bridge, API validation, job transitions, and safe path handling are covered with mocks. Real paid/quota-consuming Web and Mobile builds were not run as part of routine verification.