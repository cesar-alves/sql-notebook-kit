# Support and maintenance

- Ask usage and setup questions in GitHub Discussions when enabled.
- File a bug issue only after checking the latest supported release and include a
  minimal sanitized reproduction.
- Use a feature proposal for new behavior and explain the decision it enables.
- Use the backend preview report form for Redshift, Databricks, and BigQuery; a
  contract-test pass does not make a backend certified.
- Report security concerns only through [SECURITY.md](SECURITY.md).

Do not post credentials, database URLs, account identifiers, private query text,
notebook output, or internal hostnames. Alpha APIs may change under the documented
[versioning policy](docs/versioning.md).

## Triage and ownership

The maintainer reviews new issues at least weekly and security reports according to
the response targets in `SECURITY.md`. Use `bug`, `feature`, `backend:preview`,
`security`, and `release` to classify work; use `needs-reproduction`, `blocked`, and
`stale` only after recording the reason. Issues are not closed merely because they are
old: a maintainer may mark an inactive issue stale after 60 days, must allow at least
14 more days for a response, and must preserve accepted roadmap work.

Only a maintainer may change a backend's support level. Promotion from preview requires
the live evidence in `docs/compatibility.md`; a contract-test result alone is not
sufficient. Release-note exemptions likewise require the `release-note:exempt` label
and a written pull-request rationale.
