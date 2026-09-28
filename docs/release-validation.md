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
| VS Code | Exact VSIX in Stable, Insiders, and one remote-style host; lifecycle, persistence, reconnect, themes, fallback, and removal | Tester | Pending |
| Accessibility | Keyboard-only at 200%/640 px; focus, forced colors, non-color meaning, labels, and announced status | Tester | Pending |
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

### VS Code sign-off matrix

Run every row with the exact release VSIX. A remote-style host means SSH, WSL, or a
development container where the extension and kernel execute remotely; record which
one was used. Keep the repository private and all notebook data synthetic.

| Case | Stable local | Insiders local | Remote-style |
| --- | --- | --- | --- |
| Install or update through `sql-notebook-kit vscode install` from an editor path containing spaces | Pending | Pending | Pending |
| Activate the renderer and SQL language support in a notebook using Microsoft Jupyter | Pending | Pending | Pending |
| Run bounded eager SQL, lazy collection, and visualization create/edit/delete | Pending | Pending | Pending |
| Save, close, reopen, and rerun; verify visualization metadata persists without stale output | Pending | Pending | Pending |
| Reconnect and replace the kernel; verify the current session recovers and an old widget fails safely | Pending | Pending | Pending |
| Switch light, dark, and high-contrast themes while a table, chart, and editor are visible | Pending | Pending | Pending |
| Provoke syntax, stale-revision, and unavailable-renderer states; verify sanitized actionable messages | Pending | Pending | Pending |
| Uninstall; verify unrelated extensions, notebooks, settings, and user data remain | Pending | Pending | Pending |

Also open the documented browser-only path once and confirm `vscode.dev` is reported
as unsupported rather than appearing to install or silently degrading. Record the OS,
editor version, remote mechanism, Python and Jupyter versions, VSIX SHA-256, tester,
date, and a sanitized evidence link for each column.

### Accessibility sign-off matrix

Complete the following in JupyterLab and VS Code Stable, then repeat the theme-specific
checks in Insiders and the selected remote-style host:

- Use only the keyboard for table navigation and visualization add, preview, apply,
  edit, rename, duplicate, delete, cancel, reset, tab selection, and options expansion.
  Focus must remain visible and return to a predictable control when dialogs close.
- Repeat the complete editor flow at 200% zoom and at a 640-pixel output width. No
  required control, validation message, table value, or status may become unreachable.
- Test light, dark, native high-contrast, and browser forced-colors modes. Selection,
  validation, truncation, failure, and disabled states must not rely on color alone.
- With a screen reader or accessibility inspector, verify names, roles, descriptions,
  relationships, and current selection for inputs, tabs, tables, menus, and buttons.
- Verify loading, save, conflict, validation, empty-result, truncation, export, and
  failure status changes are programmatically announced without stealing focus.

Record the assistive technology or inspector, browser/editor versions, zoom and width,
theme or forced-colors mode, tester, date, outcome, and sanitized evidence link. Any
keyboard trap, hidden required control, unlabeled action, unannounced blocking error,
or color-only meaning is a P0 failure.

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
