# Security policy

## Supported versions

Until a later release says otherwise, only the latest published 0.x release receives
security fixes. The unreleased development branch is not a supported distribution.

## Private reporting

Use GitHub's **Report a vulnerability** form in this repository's Security tab. This
creates a private security advisory visible to maintainers. Do not include secrets,
credentials, private notebook output, or exploitable details in a public issue.

Maintainers aim to acknowledge a report within three business days, provide an initial
assessment within seven business days, and agree on a coordinated-disclosure timeline
after reproducing the issue. These are response targets, not a guarantee. Reporters
should allow a reasonable remediation window before disclosure.

If the private form is unavailable, do not open a public issue containing sensitive
details. Open a minimal issue asking a maintainer to enable a private contact route,
without describing the vulnerability.

The [security and trust model](docs/security-model.md) distinguishes intentional code
and SQL execution from security defects.
