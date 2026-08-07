# Migration from redshift-notebooks

The project was renamed before its first stable release. Install
`sql-notebook-kit`, import `sql_notebook_kit`, run the `sql-notebook-kit` CLI,
and replace configuration variables with the `SQL_NOTEBOOK_KIT_` prefix.

There are deliberately no compatibility imports, old CLI aliases, duplicate
extensions, legacy environment variables, or old comm/MIME handlers. Reinstall
the JupyterLab and VS Code companions from the new distribution.

The only automatic compatibility behavior covers saved visualization metadata.
Readers prefer `metadata.sql_notebook_kit.visualizations`, fall back to
`metadata.redshift_notebooks.visualizations`, and migrate the collection on the
next successful save. Adjacent metadata is preserved. Read-only notebooks can
use legacy state for the active session but are not reported as migrated.
