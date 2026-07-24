# Security policy

## Supported versions

GroundedPDF is currently pre-1.0. Security fixes are applied to the latest code on the `main` branch.
Older snapshots are not maintained.

## Reporting a vulnerability

Use this repository's **Security** tab to submit a private vulnerability report through GitHub's
private vulnerability reporting workflow. Do not open a public issue with exploit details, private
PDF content, credentials, or personal data.

Include the affected revision, deployment mode, reproduction conditions, impact, and the smallest
safe proof of concept. You should receive an acknowledgement within seven days. Disclosure timing
will be coordinated after the issue is reproduced and a correction is available.

GroundedPDF is a local, single-user application and must not be exposed directly to the public
internet. The complete deployment assumptions and threat model are documented in
[docs/security.md](docs/security.md).
