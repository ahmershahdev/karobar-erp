# Security policy

## Supported versions

Karobar ERP is before its first stable release (`v1.0.0`). Security fixes go to the `main` branch
and into the next release; older `v0.x` tags don't get fixes. Run the latest release, or `main`.

## Reporting a vulnerability

Please don't open a public issue or pull request for a security problem. Report it privately:

1. **GitHub (preferred):** the
   [Security tab](https://github.com/ahmershahdev/karobar-erp/security/advisories/new) of this
   repository, **Report a vulnerability**.
2. **Email:** [support@ahmershah.dev](mailto:support@ahmershah.dev) with "Security" in the subject.

Include the affected endpoint or file, steps to reproduce, and what an attacker could do with it.
Problems that let one tenant see or change another tenant's data are treated as the most serious,
and so is anything that gets past the shared demo account's limits on a demo server.
You'll get a first answer within 7 days.

How the app protects data, and the limits it knows about, are written down in
[docs/security.md](docs/security.md).
