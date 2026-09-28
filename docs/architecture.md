# Architecture overview

SQL Notebook Kit is a kernel-first library with two optional frontend companions.
The kernel owns execution, result bounds, and visualization state; frontends persist
versioned configuration and relay validated theme and metadata messages.

1. `create_session` resolves a built-in adapter, named profile, or custom synchronous
   DBAPI factory without opening a connection by default.
2. `NotebookSession.register` connects the SQLAlchemy engine to JupySQL. `%sql` and
   `%%sql` execute eagerly and return a detached, bounded `NotebookResult`.
3. Eligible SELECT results expose a `LazyQuery`. A lazy action reruns the source SQL
   through a separately owned SQLFrame connection, so it does not share transactions,
   temporary tables, or session variables with the eager path.
4. The visualization layer consumes only the bounded local frame. It never rewrites or
   reruns the source query. Visualization collection metadata is schema-versioned.
5. The JupyterLab 4 extension and bundled VS Code extension exchange size-limited,
   revisioned bridge messages. Without a companion, visualization editing remains
   session-only and says so.

Connections are acquired only when authentication or execution requires them.
`reconnect` disposes owned resources and invalidates old lazy queries; `dispose` is
idempotent and does not close caller-owned custom resources unless the factory contract
says ownership was transferred. Failed statements are never replayed automatically.

The [factory contract](factory-contract.md), [transformation guide](transformations.md),
[visualization guide](visualization.md), and [security model](security-model.md) define
the detailed boundaries.
