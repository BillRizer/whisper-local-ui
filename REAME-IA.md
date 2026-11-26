# Whisper Local — AI agent guide

## Overview

Whisper Local transcribes speech from audio or video into the original language and translates speech into **English** using `faster-whisper`. It also supports microphone recording in the web interface. Processing runs locally without an external transcription API or API key. The first use of a model may download its weights from Hugging Face.

The web interface, HTTP API, and MCP tools share the same queue, loaded model, and history.

## Start the server

On Linux, from the repository root:

```bash
./run.sh
```

The launcher creates `.venv` and installs `requirements.txt` when needed. Keep the process running while using the UI or MCP. By default, it listens on `127.0.0.1:7860`:

| Resource | Default URL |
| --- | --- |
| Web interface | `http://127.0.0.1:7860/` |
| MCP, Streamable HTTP | `http://127.0.0.1:7860/mcp` |
| System status | `http://127.0.0.1:7860/api/system` |
| Model status | `http://127.0.0.1:7860/api/model` |

Use `PORT=7861 ./run.sh` to change the port. Check that the server responds:

```bash
curl -sS http://127.0.0.1:7860/api/system
```

`HOST=0.0.0.0 ./run.sh` opts into listening on all IPv4 interfaces. The app has no authentication: network clients that reach the API can access results and submit or delete jobs, and the MCP tools can access files readable by the server when host validation permits. Keep the default loopback binding unless network access is explicitly requested, and restrict any network exposure with appropriate access controls.

For development, follow [AGENTS.md](AGENTS.md) and the instructions of your environment.

## Recommended agent workflow: MCP

Connect an MCP client to `http://127.0.0.1:7860/mcp`. Examples:

```bash
codex mcp add whisper-local --url http://127.0.0.1:7860/mcp
claude mcp add --transport http whisper-local http://127.0.0.1:7860/mcp
```

`transcribe_file` and `translate_file` accept an **absolute path readable by the server process**. A path available only in another container or computer will not work. MCP does not upload the file.

1. Call `transcribe_file` for text in the original language or `translate_file` for English. Pass `path` and, optionally, `language` (default `auto`), `model` (default `small`), and `prompt` (context or vocabulary, up to 1,000 characters). Save the returned `job_id`.
2. Call `wait_for_job(job_id, timeout_seconds=20)` until the status is `done` or `error`. Each call waits at most 30 seconds. `get_job` returns immediately. `queued` and `running` are not final states. Model downloads can take minutes; check `message` and `progress`.
3. For a completed job, call `read_transcript(job_id)`. For long transcripts, repeat with `start=next_start` until `next_start` is `null`. `max_chars` is limited to 12,000 per call.
4. To save a file, call `export_transcript(job_id, format="txt")`. Supported formats are `txt`, `srt`, `vtt`, and `json`. The tool returns the absolute path in the server's `data/exports/` directory by default.
5. On `error`, inspect and report the `error` field from `get_job` or `wait_for_job`. Do not report the job as completed.

Other tools: `list_jobs` lists history; `get_model_status` reports the loaded model, device, and unload settings; `unload_model` releases the model; `set_model_idle_timeout` sets the idle timeout in minutes (`0`, `1`, `5`, `10`, `15`, `30`, `60`; `0` disables it). An unload requested while jobs are active waits for the queue. The next job reloads the model from cache.

Models: `tiny`, `base`, `small`, `medium`, `large-v3`. Input languages: `auto`, `pt`, `en`, `es`, `fr`, `de`, `it`, `ja`, `zh`, `ko`, `ru`, `ar`, `hi`, `nl`, `pl`, `tr`, `uk`, `sv`, `id`, `vi`. Whisper translation targets **English only**.

## Web interface and HTTP API

The interface accepts up to **20 files per batch**, supports microphone recording and task/language/model selection, and displays the queue and history. Users can copy results, retry eligible failed jobs, or download TXT, SRT, VTT, and JSON. Microphone recording requires browser permission and a secure context, such as localhost or HTTPS.

For integrations without MCP:

- `POST /api/jobs`: submit `multipart/form-data` with one or more `files` and optional `task=transcribe|translate`, `language=auto`, `model=small`, and `prompt`. HTTP `202` returns queued jobs.
- `GET /api/jobs` and `GET /api/jobs/{job_id}`: inspect history and job details.
- `POST /api/jobs/{job_id}/retry`: requeue a failed job when its input remains available.
- `GET /api/jobs/{job_id}/download?format=txt`: download a completed result.
- `GET /api/export?format=txt`: download a ZIP of completed results.
- `DELETE /api/jobs/{job_id}`: remove a job from history.

Accepted extensions: MP3, MP4, M4A, M4V, WAV, FLAC, OGG, OGA, OPUS, WEBM, MOV, MKV, AVI, AAC, AIFF, WMA, MPEG, and MPGA. Each file must contain decodable audio and be no larger than **1 GB**. A single worker processes jobs sequentially.

## Operational notes

- **GPU:** `WHISPER_DEVICE=auto` selects CUDA when available and CPU otherwise. Use `WHISPER_DEVICE=cuda ./run.sh` to require CUDA. Check `/api/system` and the completed job's device.
- **CUDA libraries:** On Linux, `run.sh` adds pip-installed CUDA libraries to `LD_LIBRARY_PATH`. If `libcublas.so.12` or `libcudnn.so.9` is missing, run `.venv/bin/python -m pip install -r requirements-gpu.txt` and restart with `./run.sh`. A working NVIDIA driver is also required.
- **Large models:** `large-v3` downloads approximately 2.9 GB on first use and requires more memory. Check job `message` and `progress` before assuming a download or initialization has stalled.
- **Data:** The default data directory is `./data`, configurable with `WHISPER_DATA_DIR`. Completed results persist in `data/results/` and settings in `data/settings.json`. Successful browser uploads are deleted; failed uploads remain available for retry until the job is deleted or the server restarts. Failed jobs do not persist across restarts. Files supplied by path through MCP are preserved.
- **Network:** Transcription and translation can operate without external services once model weights are cached. Network access to the server is opt-in and has the security implications described above.

For installation and user-facing instructions, see [README.md](README.md).
