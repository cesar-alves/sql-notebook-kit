# Release playbook

This project uses `develop` for integration and `main` for released history. The
repository remains private throughout preparation, tagging, TestPyPI rehearsal, and
production publication. No workflow changes repository visibility. A maintainer may
make it public only after post-publication verification.

## Prepare

1. Open a private release issue and link evidence for every P0 requirement. Record
   each P1 deferral with an owner, rationale, risk, and target milestone. Keep access
   evidence such as registry ownership and contact-route tests outside the repository.
   Start from the Release readiness issue form and use the matrix in
   `docs/release-validation.md` so manual and automated evidence use the same release
   contract.
2. Create `release/vX.Y.Z` from protected `develop` (or `hotfix/vX.Y.Z` from protected
   `main` for an urgent patch). Synchronize every manifest, finalize the dated
   changelog, rebuild frontend assets, and run
   `uv run python scripts/validate.py`.
3. Open a pull request to `main`, add `ci:merge-ready`, and require all protected
   checks. The release-policy check rejects every other source branch or version.
4. Complete the manual VS Code and accessibility matrices in the private release
   record. Confirm license ownership, dependency-license review, cloud preview results,
   PyPI namespace control, the private reporting route, and zero unreviewed high or
   critical findings.
5. Merge with a merge commit. Do not squash or rebase the release boundary.

## Tag and rehearse

Create an annotated, signed tag on the exact `main` merge commit and push it:

```bash
git switch main
git pull --ff-only
git tag -s vX.Y.Z -m "SQL Notebook Kit vX.Y.Z"
git push origin vX.Y.Z
```

The tag workflow verifies GitHub's signature record and tag/version/commit agreement,
builds wheel and sdist once, validates content and licenses, creates SHA-256 hashes and
SBOMs, publishes to TestPyPI through trusted publishing, and installs those artifacts
from TestPyPI. It never publishes to production PyPI.

## Publish

A named maintainer inspects the successful tag workflow, TestPyPI package, smoke logs,
hashes, SBOMs, and private evidence. They then dispatch the production workflow with
the signed tag and source workflow-run ID. The workflow confirms that the successful
run belongs to the tag's exact commit, downloads its immutable bundle, verifies every
hash, publishes through the `pypi` trusted-publishing environment, and creates the
GitHub Release. This dispatch is the human authorization record.

After publication, install from production PyPI in a clean environment, run the
documented DuckDB/Jupyter/VSIX smokes, verify release assets and links, merge `main`
back into `develop` by pull request, and delete the release branch. Only then may a
maintainer manually make the repository public and enable public-only GitHub security
features and attestations.

## Incorrect releases

Released files are immutable. Stop promotion when an installation, security,
licensing, or data-exposure defect appears. Preserve sanitized evidence, revoke or
rotate affected access, yank the PyPI release when appropriate, publish an advisory,
and issue a new patch version. Retry only byte-identical artifacts when registry state
permits; any code correction requires a new version.
