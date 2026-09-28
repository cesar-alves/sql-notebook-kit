# Distribution artifact contract

The release build creates each Python artifact once. Validation, TestPyPI rehearsal,
production publication, and GitHub Release assembly consume those exact files and the
recorded SHA-256 manifest; no downstream job rebuilds them.

## Wheel

The platform-independent wheel contains the Python runtime, `py.typed`, visualization
CSS, one embedded VSIX, the root MIT license in distribution metadata, and exactly one
JupyterLab prebuilt-extension payload under Jupyter shared data. It excludes tests,
documentation sources, examples, caches, local files, credentials, source maps, and
frontend build sources. Installing this wheel never invokes Node.js or pnpm.

## Source distribution

The sdist contains Python sources, build metadata and hook, root license/readme/
changelog, user documentation and sanitized examples, pnpm lock/workspace manifests,
frontend sources, and the staged JupyterLab and VS Code artifacts needed to build a
wheel without a frontend toolchain. The single included build utility normalizes VSIX
ZIP metadata so rebuilding in different checkout paths produces identical frontend
artifacts. It excludes tests, `.env`, `local/`, VCS data, caches, `dist/`, `site/`,
`node_modules/`, raw package-manager VSIX output, and local frontend output.

## Frontend artifacts

The JupyterLab bundle contains its manifest, install metadata, compiled chunks, and
generated third-party license inventory. The embedded VSIX contains compiled extension
and renderer code, syntax data, its manifest, MIT license, and required notices. It is
installed through `sql-notebook-kit vscode install`; separate Marketplace publication
is outside the 0.1.0 scope.

Artifact tests enforce these allowlists, version agreement, license presence, absence
of local paths in source maps, clean installation/discovery, CLI smoke behavior, and
uninstall ownership.
