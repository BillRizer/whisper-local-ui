# Whisper Local — AI agent instructions

## What this application does

It transcribes speech from audio or video into text in the original language and translates speech into **English** with `faster-whisper`. It also supports microphone recording in the web interface. Processing takes place on the local computer without an external API or key; the first use of each model may download its weights from Hugging Face.

The same server has three entry points: web interface, HTTP API, and MCP tools. All share the processing queue, loaded model, and history.

## Start and locate the server

From the project root on Linux, run:

```bash
./run.sh
```

`run.sh` creates `.venv` and installs dependencies from `requirements.txt` when needed. Keep the process running while using the UI or MCP. By default, the server listens only on `127.0.0.1`, port **7860**:

| Resource | Default address |
| --- | --- |
| Web interface | `http://127.0.0.1:7860/` |
| MCP, Streamable HTTP transport | `http://127.0.0.1:7860/mcp` |
| System status | `http://127.0.0.1:7860/api/system` |
| Model status | `http://127.0.0.1:7860/api/model` |

To change the port, start with `env PORT=7861 ./run.sh` and use the new port in all addresses. To check that the server responds:

```bash
curl -sS http://127.0.0.1:7860/api/system
```

For agent-assisted development, see [AGENTS.md](AGENTS.md). Instructions for the current environment also apply.

## Recommended AI access: MCP

Connect the MCP client to `http://127.0.0.1:7860/mcp`. Registration examples:

```bash
codex mcp add whisper-local --url http://127.0.0.1:7860/mcp
claude mcp add --transport http whisper-local http://127.0.0.1:7860/mcp
```

The client and server need access to the **same filesystem**: `transcribe_file` and `translate_file` accept an **absolute** path readable by the server process, such as `/home/user/Videos/meeting.mp4`. A path that exists only in another container or computer will not work. MCP does not upload the file.

Workflow:

1. Call `transcribe_file` for text in the original language or `translate_file` for text in English. Pass `path` and optionally `language` (default `auto`), `model` (default `small`), and `prompt` (context or vocabulary, up to 1,000 characters). Save the returned `job_id`.
2. Call `wait_for_job(job_id, timeout_seconds=20)` until `status` is `done` or `error`. Each call accepts at most 30 seconds. `get_job` provides an immediate query; `queued` and `running` are not final results. The first model download can take minutes; inspect `message` and `progress`.
3. If `done`, call `read_transcript(job_id)` to get the text. For long transcripts, repeat with `start=next_start` until `next_start` is `null`. The `max_chars` limit is 12,000 per call.
4. If a file is needed, call `export_transcript(job_id, format="txt")`. Formats are `txt`, `srt`, `vtt`, and `json`; the tool returns the absolute path saved under `data/exports/`.
5. If `error`, read the `error` field from `get_job`/`wait_for_job` and report the failure. Do not treat the job as complete.

Other tools: `list_jobs` lists history; `get_model_status` reports the loaded model, device, and unload time; `unload_model` releases the model from memory; `set_model_idle_timeout` configures automatic unloading (minutes: `0`, `1`, `5`, `10`, `15`, `30`, `60`; `0` disables it). If work is active, unloading waits for the queue to finish. The next use reloads the model from cache.

Available models: `tiny`, `base`, `small`, `medium`, `large-v3`. Accepted languages: `auto`, `pt`, `en`, `es`, `fr`, `de`, `it`, `ja`, `zh`, `ko`, `ru`, `ar`, `hi`, `nl`, `pl`, `tr`, `uk`, `sv`, `id`, `vi`. Whisper translation is always **into English**, not an arbitrary target language.

## UI and HTTP API

The UI supports up to **20 files per batch**, microphone recording, task/language/model selection, queue monitoring, copying results, and downloading TXT, SRT, VTT, or JSON. History is in the sidebar. Recording requires browser microphone permission and access through `localhost`.

For integration without MCP, `POST /api/jobs` accepts `multipart/form-data` with a `files` field (one or more files) and optional fields `task=transcribe|translate`, `language=auto`, `model=small`, and `prompt`. The HTTP `202` response contains queued jobs. Use `GET /api/jobs/{job_id}` to retrieve a result, `GET /api/jobs/{job_id}/download?format=txt` to download one result, and `GET /api/export?format=txt` to download a ZIP of completed results. `DELETE /api/jobs/{job_id}` removes a history record.

Accepted extensions: MP3, MP4, M4A, M4V, WAV, FLAC, OGG, OGA, OPUS, WEBM, MOV, MKV, AVI, AAC, AIFF, WMA, MPEG, and MPGA. The file must contain decodable audio and be at most **1 GB**. The queue uses one worker; multiple jobs run sequentially.

## Operational details

- **GPU:** `WHISPER_DEVICE=auto` uses CUDA when available and CPU otherwise. To require CUDA, start with `env WHISPER_DEVICE=cuda ./run.sh`. Check the device at `/api/system` and the device actually used in the job result.
- **CUDA libraries:** on Linux, prefer `run.sh`, which adds pip-installed CUDA libraries to `LD_LIBRARY_PATH`. If `libcublas.so.12` or `libcudnn.so.9` is missing, install `requirements-gpu.txt` in `.venv` and restart using the script: `.venv/bin/python -m pip install -r requirements-gpu.txt`. The NVIDIA driver must also work.
- **Large models:** `large-v3` downloads about 2.9 GB on first use and uses more memory. Download and initialization can take time; monitor the job's `message`/`progress` before concluding it is stuck.
- **Data:** the default is `./data` (change with `WHISPER_DATA_DIR`). Completed results persist in `data/results/`; settings are stored in `data/settings.json`. UI uploads are deleted after processing. Files supplied by path through MCP are preserved.
- **Network:** the service is restricted to `127.0.0.1` by default. Keep MCP local because it can read files accessible to the process. Once weights are cached, transcription and translation work without a connection to external services.

For installation and human usage details, see [README.md](README.md).
