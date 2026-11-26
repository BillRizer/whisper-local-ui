# Contributing and AI use

Describe the problem, scope, and acceptance criteria before significant changes. Read `AGENTS.md`, the PRD, architecture, and risks; use an ADR for decisions that are difficult to reverse or change boundaries and responsibilities. Reconstructed decisions are not evidence of prior discussion.

In the PR, explain the old and new behavior, decisions, tests run and results, risks, and gaps. Disclose significant AI use and what a person reviewed, without revealing prompts, personal data, or secrets. The responsible person must review code and tool outputs and own the integration decision. Do not claim review, approval, or testing that did not happen. For defects, include reproduction steps and a regression test when feasible.

Before integration, check scope, sensitive data, compatibility, tests, and affected documentation. Automated CI complements review; it does not replace tests with a real model or security analysis.
