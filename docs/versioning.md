# Alpha versioning and deprecation policy

SQL Notebook Kit uses Semantic Versioning. The 0.x line is explicitly API-unstable:
a minor alpha release may contain breaking changes when the changelog and release
notes identify the affected advertised behavior and a migration path.

The project applies these rules before 1.0:

- every user-visible breaking change appears in the changelog and release notes;
- removal or incompatible change of an advertised Python API is called out even when
  Semantic Versioning permits it in a 0.x minor release;
- deprecation is preferred when it is safe and proportionate, but security or data
  integrity fixes may require an immediate break with an explicit migration note;
- serialized notebook metadata always carries a schema version; readers validate it
  and migration is explicit rather than inferred from shape;
- persisted metadata migrations are one-way and tested, while session identifiers,
  live connections, result frames, credentials, and theme state remain session-only;
  and
- released artifacts are immutable. A defective release is yanked or superseded by a
  new patch release; its files are never replaced.

See the [changelog](https://github.com/cesar-alves/sql-notebook-kit/blob/main/CHANGELOG.md),
[migration guide](migration.md), and
[compatibility contract](compatibility.md).
