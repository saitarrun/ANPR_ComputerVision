# Security Pre-commit Setup

This document describes the secrets scanning and security checks configured for this project.

## Overview

The project uses multiple security tools integrated via pre-commit hooks to prevent credential leaks and detect security issues before they reach version control:

- **detect-secrets** — Scans for hardcoded secrets (API keys, passwords, tokens)
- **bandit** — Analyzes Python code for common security issues
- **pip-audit** — Checks dependencies for known vulnerabilities
- **gitleaks** — Detects secrets using pattern matching (already installed)
- **ruff (S rules)** — Linting-based security checks (already integrated)

## Installation

Install pre-commit hooks:

```bash
pre-commit install
```

This will automatically run all security checks before each commit.

## Running Locally

### Run all pre-commit hooks

```bash
pre-commit run --all-files
```

### Run specific hooks

```bash
# Detect secrets only
pre-commit run detect-secrets --all-files

# Bandit security analysis
pre-commit run bandit --all-files

# Dependency vulnerability scan
pre-commit run pip-audit --all-files

# Gitleaks
pre-commit run gitleaks --all-files
```

## Secrets Baseline

The `.secrets.baseline` file contains known secrets (false positives or legitimate test data). When a new legitimate secret is discovered:

1. Verify it is **not** a real production credential
2. Add to baseline:
   ```bash
   detect-secrets scan --baseline .secrets.baseline --update
   ```
3. Review the diff before committing
4. Commit the updated baseline

**Never** commit real credentials. Use environment variables or secrets management instead.

## Committing Without Checks (Emergency Only)

If you need to bypass pre-commit checks **temporarily**:

```bash
git commit --no-verify
```

**⚠️ WARNING:** This disables ALL pre-commit checks. Only use if:
- A legitimate secret cannot be extracted before commit (emergency)
- You will immediately run `git revert` or `git reset` if a secret leaks
- You have authorization to bypass security checks

**Best practice:** Never use `--no-verify` for production commits. Rotate any credentials that were committed.

## CI/CD Integration

GitHub Actions runs all pre-commit checks on every push and pull request:

1. **Lint job** — Runs ruff, mypy
2. **Security job** — Runs pip-audit and filesystem scanning
3. **Pre-commit checks** — Runs all hooks before merge

Pull requests fail if any security check fails.

## Bandit Configuration

Bandit is configured to:
- **Skip tests** — `B101` (assert_used) is allowed in test files
- **Exclude test directories** — `/tests` and `/migrations` are not scanned
- **Check all production code** — `anpr_core`, `api`, `ingest`, `workers`, `db`

Common false positives:
- Hardcoded test IPs (127.0.0.1)
- Test passwords in fixtures
- Use of `assert` in tests

Override with `# nosec` comment if necessary:

```python
import pickle
pickle.loads(untrusted_data)  # nosec: test data only
```

## Dependency Auditing

`pip-audit` checks for known vulnerabilities in dependencies. If a vulnerability is found:

1. Check if the package has been updated:
   ```bash
   pip list --outdated
   ```
2. Update the package in `pyproject.toml`
3. Run `uv sync` to update lock file
4. Verify tests still pass

If no update is available, use the advisory code to skip:

```bash
pip-audit --skip-advisory ADVISORY_CODE
```

## Common Issues

### "Secret found in baseline" error

If detect-secrets finds a secret:

1. **If legitimate test data:** Update baseline with `detect-secrets scan --baseline .secrets.baseline --update`
2. **If real credential:** Never commit it. Rotate the credential immediately, remove from code, and commit a fix.

### Bandit false positive

If bandit flags secure code:

```python
# Override with nosec comment
dangerous_function()  # nosec: intentional, safe in this context
```

Document why the override is safe in a comment.

### Pre-commit hook timeout

If a hook times out (scanning large files):

- Run it manually to see progress: `uv run bandit -r anpr_core`
- Optimize if needed (e.g., exclude large data files)

## Updating Security Tools

To update pre-commit hooks, modify `.pre-commit-config.yaml` and run:

```bash
pre-commit autoupdate
```

Then verify all checks pass:

```bash
pre-commit run --all-files
```

## References

- [detect-secrets](https://github.com/Yelp/detect-secrets)
- [bandit](https://bandit.readthedocs.io/)
- [pip-audit](https://github.com/pypa/pip-audit)
- [gitleaks](https://gitleaks.io/)
- [Pre-commit framework](https://pre-commit.com/)
