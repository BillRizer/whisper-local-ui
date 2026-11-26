# PRD — Whisper Local

Status: reconstructed from the existing code and README on 2026-11-25; this does not represent historical approval. Product owner and metrics have not yet been defined.

## Problem and audience

People and local agents need to convert speech from audio or video into text without sending content to a transcription API. Users operate the web interface; automation clients can use MCP or HTTP on the same computer.

## Goal and current scope

- Transcribe in the original language or translate speech into English using faster-whisper locally.
- Accept batches of up to 20 uploads of up to 1 GB each, browser microphone recordings, and local paths through MCP.
- Track a sequential queue and retrieve results, including completed results after restart.
- Export TXT, SRT, VTT, and JSON; control model unloading.

Currently out of scope: multi-user collaboration, authentication, translation to arbitrary target languages, and guaranteed recognition accuracy. First use may download model weights; local processing does not imply no network traffic at all.

## Acceptance criteria

1. A valid upload returns a queued job; its status progresses to completion or a retrievable error. Invalid inputs are rejected.
2. Completed results can be retrieved after restart and exported in supported formats; users can remove records.
3. Temporary uploads are removed after success, job deletion, or restart; failed jobs can be requeued while their input is available. Original files specified through MCP are preserved.
4. The service binds to loopback by default and permits explicit configuration of the listening address; MCP shares the queue and history with the interface.
5. The interface distinguishes transcription from translation into English and displays progress and failures.

Automated tests cover some criteria with a simulated backend; recording, real recognition accuracy, GPU, and visual experience require manual validation. See `testes.md`.

## Open questions

Define the priority audience, measurable quality and time targets, retention policy, supported platforms, and accessibility criteria with the product owner. No user data or success metrics are available in this repository.
