# Compatibility matrix

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
