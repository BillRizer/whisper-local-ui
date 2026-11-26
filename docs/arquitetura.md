# Architecture and boundaries

State observed on 2026-11-25; reconstructed decisions are in [ADR 0001](adr/0001-arquitetura-local.md).

```mermaid
flowchart LR
  U[Browser] --> API[FastAPI]
  C[Local MCP client] --> API
  API --> Q[JobManager: in-memory queue, one worker]
  Q --> W[faster-whisper / CTranslate2]
  Q --> D[(Local uploads, results, and settings)]
  W -. first download .-> H[Cache / Hugging Face]
```

`app.py` serves the interface and API; `mcp_server.py` uses the same manager; `jobs.py` coordinates the queue and persistence; `transcription.py` loads the model and formats results; `media.py` validates files. `static/` contains the interface. Completed results are stored as JSON; the queue, errors, and in-progress jobs are not recovered after restart. Leftover uploads are removed on startup. MCP exports remain in `data/exports/` and are not automatically removed when a job is deleted.

Failed uploads remain temporarily on disk for retry and are removed after success, job deletion, or restart. Local files supplied through MCP are not deleted.

The API/MCP has no authentication. The launcher binds to loopback by default, but `HOST` allows listening on other interfaces. Any client that can access the API can read results and submit jobs; MCP can read files accessible to the process when host validation permits. Loopback does not isolate other local processes. Network exposure requires external access restrictions and increases the risks described in [ADR 0002](adr/0002-endereco-de-escuta.md). Results and exports may contain sensitive data; permissions and backups depend on the environment.

The in-memory queue and shared model assume a single application process. Do not start multiple workers against the same data directory without redesigning coordination, recovery, and concurrent writes. Abrupt failures can leave temporary files; there is no transactional guarantee across all steps.
