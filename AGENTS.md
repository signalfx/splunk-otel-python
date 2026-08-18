# Repository Instructions

## Python validation

- Before committing or pushing Python changes, run `hatch fmt --check`. The CI
  workflow uses Hatch's generated static-analysis configuration for both Ruff
  linting and formatting.
- Do not substitute a targeted `hatch run ruff check` command for this check. It
  can use different rules and does not validate formatting.
