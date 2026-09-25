# Compatibility matrix

This document is the canonical compatibility contract for the 0.1.0 alpha.
The release tests verify Python classifiers and frontend manifests against these
values. Changes to support require this document, the changelog, and those manifests
to change together.

## Supported runtimes and frontends

| Component | Supported contract |
| --- | --- |
| Python | 3.11, 3.12, 3.13, and 3.14 |
| JupyterLab | Major version 4 |
| VS Code | 1.100.0 or newer, desktop or a workspace extension host |
| VS Code Jupyter | Required companion extension |
| `vscode.dev` | Unsupported; no local/workspace Python extension host |

Only CPython is exercised for 0.1.0. Supported means the release suite passes on
the stated version; it does not extend support to end-of-life operating systems.

## Dependency certification

During the alpha series, release certification covers the exact Python and
JavaScript dependency graphs recorded in `uv.lock` and `pnpm-lock.yaml`. Declared
lower bounds describe the intended install range, but minimum-version combinations
are not separately certified yet. Security and compatibility fixes update the
locks, and each release is rebuilt and tested from those committed resolutions.

## Backend support tiers

Support labels describe evidence for this release, not similarity between SQL dialects.

| Backend | Level | Eager SQL | Lazy SQLFrame | Rollback after error | Live validation |
| --- | --- | --- | --- | --- | --- |
| DuckDB 1.5 | Certified | Yes | Yes | Yes | 2026-08-07, local PR suite |
| Amazon Redshift | Preview | Yes | Yes, community SQLFrame backend | Yes | Pending release credentials |
| Databricks SQL | Preview | Yes | Yes | Capability-disabled | Pending release credentials |
| Google BigQuery | Preview | Yes | Yes | No | Pending release credentials |
| Custom DBAPI factory | Best effort | Contract dependent | Opt-in factory | Declared by current contract | User-owned |

The portable transformation guarantee covers only operations exercised by the
shared test matrix. Backend-specific SQLFrame functions remain upstream behavior.
Cloud adapters become certified only after authentication, eager execution,
failure recovery, representative types, lazy execution, bounded collection,
visualization, and cleanup pass against a live service.

A unit or contract-test pass never constitutes live-service certification. Preview
backends may be useful, but their authentication and service behavior have not met the
release certification bar. Custom synchronous DBAPI factories are best effort and
must obey the [connection ownership contract](factory-contract.md).
