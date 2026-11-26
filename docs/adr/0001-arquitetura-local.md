# ADR 0001 — Local processing and shared queue

Status: reconstructed on 2026-11-25 from the existing implementation; there is no record of when or by whom the original decision was made.

## Context

The interface and MCP need to run transcription on the computer and share state without relying on an external transcription API.

## Observed decision

FastAPI hosts the UI, API, and MCP in the same process; a `JobManager` serializes jobs in one worker and reuses a faster-whisper model. Uploads are temporary; completed results are persisted locally. Weights may be downloaded on first use.

## Consequences and alternatives

This simplifies deployment and reduces contention for the model, but limits throughput, loses the queue on restart, and requires care with local data. A persistent queue with separate processes would make recovery and scaling easier at the cost of infrastructure and coordination; there is no evidence this alternative was formally evaluated originally. Changes to this decision require a new ADR and migration and concurrency tests.
