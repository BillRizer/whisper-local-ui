# Risks and outstanding work

Initial register dated 2026-11-25; priorities are a technical assessment, not delivery commitments.

| Risk | Impact and status | Suggested next action |
| --- | --- | --- |
| Unauthenticated API/MCP | Other local processes can access data and files; `HOST=0.0.0.0` increases exposure to network clients. | Keep loopback as the default, restrict access with a firewall, and design authentication and authorization. |
| Persisted data | Transcripts and exports may be sensitive; deleting history does not remove MCP exports. | Define retention, deletion, and permissions; document backups. |
| Volatile queue | Restart loses pending and running jobs. | Evaluate persistence and recovery against product criteria. |
| Large and multiple uploads | Up to 20 GB per batch can consume disk; synchronous upload may affect responsiveness. | Evaluate quotas, free space, and real load. |
| Dependencies with open ranges | Future installations may vary and introduce regressions. | Adopt a reproducible lock and update policy after choosing platforms. |
| Quality and reliability | Simulated tests do not measure recognition, GPU, or usability. | Define a consented evaluation set and reproducible manual tests. |
| Origin and review | The initial repository had no commit history; there is no evidence of earlier review. | Record reviews and verification from this point onward. |
