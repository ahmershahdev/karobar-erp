# Contributing

Karobar ERP is in its planning stage. Issues and ideas are welcome; for code, please open an issue
first so we can agree on the approach. Questions go to
[Discussions](https://github.com/ahmershahdev/karobar-erp/discussions).

## Pull requests

- One change per pull request, into `main`, squash-merged.
- Branch names: `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Tests and linters must pass. Business logic in `backend/apps/core` needs 100% branch coverage.
- New tenant-owned endpoints need an isolation test (another tenant's data is `404`).
- Never put real customer, supplier or employee data in issues, tests or seed data.
- Read [AGENTS.md](AGENTS.md) for the code rules and [docs/](docs/) for the design.
