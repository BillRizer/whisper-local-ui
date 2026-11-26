# ADR 0002 — Configurable listening address

Status: implemented on 2026-11-25.

## Context

The user wants to access the interface from other devices on the local network. The original launcher binds only to loopback; the API and MCP have no authentication.

## Decision

The launcher accepts `HOST` and defaults to `127.0.0.1`. Explicitly setting `0.0.0.0` makes the server listen on all IPv4 interfaces. The launcher warns that authentication is absent; the README recommends restricting access with a firewall. This setting does not change MCP host validation or add authentication.

## Security assessment and consequences

Exposure allows clients able to reach the API to read results, submit and remove jobs, and consume resources. Where MCP host validation permits access, its tools can read files accessible to the process. The option provides no user isolation, encryption, or access control; it is unsuitable for untrusted networks or the internet without external protections. Loopback remains the default. Microphone recording in a remote browser may require HTTPS. A safer alternative is to keep loopback and use an authenticated tunnel; integrated authentication is outside the scope of this change.
