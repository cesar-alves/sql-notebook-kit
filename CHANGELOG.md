# Changelog

## 0.1.0

- Generalize the alpha project as SQL Notebook Kit with neutral Python,
  frontend, CLI, configuration, metadata, MIME, comm, and CSS identities.
- Add capability-driven built-in Redshift, DuckDB, Databricks, and BigQuery
  adapters while retaining custom synchronous DBAPI factories.
- Add one-way legacy visualization metadata migration; old imports, CLI names,
  environment variables, MIME types, and extension IDs are intentionally unsupported.

- Add an optional, separately owned SQLFrame transformation channel and expose
  eligible managed SQL results as the source-only `_df` `LazyQuery` wrapper.
- Add bounded lazy collection and visualization, SQL compilation, immutable
  transformations, reconnect invalidation, ownership guards, and explicit
  result disclosures for rerun and ineligible-query behavior.

- Support managed one-line and standalone-marker multiline `%sql` alongside
  `%%sql`, add Redshift-aware editor highlighting, and collapse sanitized SQL
  diagnostics behind the concise Redshift message.
- Complete dark/high-contrast styling for current ipywidgets controls and add
  toolbar PNG export through JupyterLab and VS Code save surfaces.
- Restore VS Code visualization metadata after rerunning saved SQL cells and
  replace stale saved widget-model errors with a clear rerun placeholder.

- Bundle the hardened VS Code companion in the Python wheel and add
  `sql-notebook-kit vscode install/status/path` commands.
- Correct VS Code cell matching and transport, validate bridge messages, and
  add deferred save acknowledgements, conflict recovery, and theme updates.
- Export the VS Code notebook renderer as an ES module and follow live VS Code
  light, dark, and high-contrast theme categories with matching fallbacks.
- Serialize VS Code kernel callbacks, recover across busy or replaced kernels,
  and retry callback errors before falling back to session-only metadata.
- Redesign result rendering with a top tab strip, content-sized table columns,
  muted row-count footers, contextual visualization actions, and fully themed
  name and Options controls.

- Define a synchronous DBAPI connection-factory contract and managed notebook session.
- Add named profiles, environment/secret resolution, and reference browser SSO factories.
- Add bounded `NotebookResult` output and optional Plotly/ipywidgets visualization.
- Require pandas 3.0.5 or newer for visualization and cover pandas 3 dtype,
  copy-on-write, aggregation, export, and rendering behavior.
- Add reusable factory contract testing, public API documentation, and package quality gates.
- Roll back failed managed `%%sql` transactions so one SQL error does not poison
  the rest of the notebook session.
- Replace the alpha single-chart editor with a registry-backed workspace for
  twelve visualization types, strict versioned specifications, deterministic
  local transformations, named collection CRUD, live themes, and safe schema
  drift handling.
- Bundle a JupyterLab 4 metadata/theme companion and add a VS Code companion
  package using the shared revisioned persistence protocol.
- Declare `nbformat` in the visualization extras so Plotly graphs render through
  the notebook MIME path in clean kernel environments.
