# Security and trust model

SQL Notebook Kit intentionally executes arbitrary notebook code and user-authored SQL.
It is not a sandbox. Open notebooks, install extensions, and connect to databases only
when you trust the code, metadata, outputs, dependencies, and target system.

| Boundary | Trusted input and validation | Failure behavior | Owning evidence / residual risk |
| --- | --- | --- | --- |
| Kernel and SQL execution | The user intentionally supplies Python and SQL. Result rows are bounded before local rendering. | Database errors are sanitized; failed statements are not replayed and capable adapters recover their transaction. | Engine and result tests. Query cost and destructive SQL remain user-owned. |
| Notebooks and outputs | Versioned namespaced metadata is shape-, revision-, and size-validated. Frontends bind messages to a cell and session. | Malformed, stale, conflicting, or oversized state is rejected or falls back to session-only mode. | Protocol, metadata, and frontend tests. An untrusted notebook can still execute code when run. |
| Connection factories | Built-ins declare capabilities and ownership. Custom factories are synchronous, explicit, and best effort. | Optional dependencies fail with installation guidance; owned resources are disposed. | Adapter contract and cleanup tests. Factory code has kernel privileges. |
| Credentials | Named profiles reject password, token, secret, and key fields. Secrets are resolved at connection time from user-controlled providers or environment variables. | Representations and user-facing errors omit credential values. | Configuration and safe-representation tests. Database drivers may have their own logging behavior. |
| Frontend bridge | Messages have a protocol version, operation allowlist, request/session/cell identity, revision rules, and payload limits. | Invalid messages receive a bounded error or are ignored; conflicts require refresh rather than overwrite. | Python and TypeScript protocol tests. A compromised extension host can observe notebook content. |
| HTML, charts, and export | Library HTML is escaped; Plotly receives bounded structured data; filenames and clipboard payloads are normalized by the companion. | Unsafe or unsupported values render as text or produce a sanitized error. | Visualization, copy, renderer, and export tests. Plotly and host rendering remain dependencies. |
| Resource usage | Eager and lazy collection enforce configured row bounds. Preview work is debounced and stale work is discarded. | Oversized bridge messages fail; users must explicitly allow larger results. | Bounds and race tests. SQL compute cost and kernel memory remain user-controlled. |
| Build and dependencies | Locked Python/JavaScript graphs, generated-asset drift checks, immutable CI actions, audit jobs, artifact allowlists, hashes, and SBOMs protect release inputs. | Release stops on drift, high/critical unreviewed findings, or artifact mismatch. | Merge-ready and release workflows. Registry or toolchain compromise is residual supply-chain risk. |
| Editor subprocesses | The CLI discovers an allowlisted editor command or uses an explicit executable path and fixed arguments. | Missing executables, malformed VSIX files, and subprocess errors fail without printing secrets. | CLI tests. The selected editor executable is trusted local code. |

SQL Notebook Kit adds no telemetry. Connection objects and bounded result data remain
in kernel memory. Versioned visualization configuration may be written to notebook
metadata; credentials, result frames, live connections, session identifiers, and theme
state must not be persisted there. Data is sent only to the database and frontend that
the user configures.

Report vulnerabilities through the private route in the repository's
[security policy](https://github.com/cesar-alves/sql-notebook-kit/security/policy),
never through a public issue.
