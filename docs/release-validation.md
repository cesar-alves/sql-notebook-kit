# Release validation record

The private release issue is the source of truth for sign-off evidence. Copy this
matrix into that issue for every release; link sanitized logs or artifacts rather
than credentials, private paths, screenshots containing customer data, or raw package
manager reports.

| Gate | Required evidence | Owner | Status |
| --- | --- | --- | --- |
| Linux CI | Python 3.11–3.14, frontend, docs, packaging, security | Release engineer | Pending |
| macOS wheel | Exact CI wheel install, import, CLI, DuckDB, Jupyter discovery | Release engineer | Pending |
| Windows wheel | Exact CI wheel install, import, CLI, DuckDB, Jupyter discovery | Release engineer | Pending |
| JupyterLab browser | Open a notebook, run eager and lazy SQL, render a bounded table, verify stale/conflict/error states | Tester | Pending |
| VS Code | Install the exact VSIX into Stable and Insiders, run SQL and visualization paths, uninstall cleanly | Tester | Pending |
| Accessibility | Keyboard-only navigation, visible focus, readable empty/error states, contrast, screen-reader labels | Tester | Pending |
| DuckDB | Certified suite and quickstart pass | Backend owner | Pending |
| Redshift preview | Supported auth paths, bounded query, cancel/error behavior | Backend owner | Pending |
| Databricks preview | Supported auth paths, bounded query, cancel/error behavior | Backend owner | Pending |
| BigQuery preview | Supported auth paths, bounded query, cancel/error behavior | Backend owner | Pending |
| Licensing | Ownership confirmed; dependency exceptions reviewed; SBOM schema valid | Maintainer | Pending |
| Security | Secret scan, SAST, dependency audit, private-reporting route test | Security owner | Pending |
| Registries | PyPI/TestPyPI namespace and trusted publishers controlled by named maintainers | Maintainer | Pending |
| Rehearsal | Signed tag, exact artifacts, TestPyPI install smoke, hashes retained | Release engineer | Pending |
| Production | Manual approval, exact rehearsal bundle, PyPI smoke, GitHub Release links | Maintainer | Pending |

## Manual UI procedure

Use the same minimal notebook on every platform. Configure credentials only through
environment variables or the backend's supported identity provider. Execute an eager
query, construct and collect a lazy transformation, render a result below the documented
row and byte limits, then provoke a syntax error and a stale-result conflict. Confirm
that messages are actionable and contain no connection strings or secret values.

For VS Code, test both Stable and Insiders with an editor executable located in a path
containing spaces. Record the editor versions and VSIX SHA-256. For JupyterLab, record
the browser and JupyterLab versions and the wheel SHA-256. Finish both matrices by
uninstalling and confirming that unrelated extensions and user files remain intact.

## Deferrals and failures

A P0 gate cannot be waived. For each P1 deferral, record its owner, rationale, user
risk, compensating control, and target milestone. Stop release promotion for an
installation, security, licensing, provenance, data-exposure, or artifact-identity
failure; follow the incorrect-release procedure in `RELEASING.md` if publication has
already occurred.

## Preview-backend cadence and report

Run credential-backed preview suites before every alpha release and at least once per
quarter while a backend remains advertised. Scheduled validation runs only from a
protected manual or scheduled workflow context; forked pull requests never receive
cloud credentials. A missed or failed run leaves the backend at preview and must be
recorded as a known gap—it never inherits DuckDB certification.

For each backend, record the validation date, connector and service versions,
authentication mode, supported execution and rollback capabilities, eager and lazy
bounded-result outcomes, visualization outcome, cleanup result, and sanitized known
gaps. Do not record account identifiers, hostnames, query text, result data, or secret
names/values. The backend owner proposes a support-level change and the maintainer
approves it against `docs/compatibility.md`.
