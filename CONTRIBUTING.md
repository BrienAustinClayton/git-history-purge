# Contributing to remove-secrets-from-git-history

Thanks for wanting to help. This project removes leaked secrets from git history, and every improvement makes that safer for someone. By taking part, you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- Report a bug or ask for a feature with an [issue form](https://github.com/BrienAustinClayton/remove-secrets-from-git-history/issues/new/choose).
- Improve the docs, the README or the error messages.
- Add or improve a detection rule.
- Add tests.
- Fix an open issue.

To report a security problem, follow the [Security Policy](SECURITY.md). Do not open a public issue.

## Set up your development environment

1. Clone the repository and open the folder.
2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows, activate it with `.venv\Scripts\activate`.

3. Install the package with the development tools:

   ```bash
   pip install -e ".[dev]"
   ```

4. For the end-to-end integration test, also install git 2.45 or newer, `git-filter-repo` and `gitleaks` 8.19 or newer. You can skip this if you only run the quick tests.

## Run the tests

Check the code style:

```bash
ruff check .
```

Run the quick tests (no gitleaks or git-filter-repo needed):

```bash
pytest -m "not integration"
```

Run everything, including the end-to-end test:

```bash
pytest
```

## Where things live

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a map of the code, a diagram of the steps, and recipes for common changes.

## Code style

- Python 3.11 or newer.
- Standard library only. Please do not add new runtime dependencies.
- Use descriptive names for functions and variables.
- Do not add comments in code. If something is unclear, rename it instead.
- Write guard conditions as named booleans, for example `remote_changed_since_fetch`, then act on them.
- Keep modules small and focused on one context.

## Add a detection rule or a new step

- **Detection rule:** patterns, placeholders and common words live in `git_history_purge/detection/rules.py`. A new place to look for secrets is a collector in `git_history_purge/detection/sources.py`. Default regexes and file names live in `git_history_purge/defaults.py`.
- **New step:** create a module in `git_history_purge/steps/`, register it in `git_history_purge/steps/__init__.py`, and add any options in `git_history_purge/cli.py`.

The [architecture guide](docs/ARCHITECTURE.md) has step-by-step recipes for both.

## Test safely

> [!WARNING]
> Test with throwaway repositories only. Never point a test at a real remote, and never use real secrets. Use fake values like `FAKE_TOKEN_123`.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) with one short line, for example:

- `feat: add a detection source for .npmrc files`
- `fix: keep tags when rewriting history`
- `docs: explain the rehearse step`

## Open a pull request

Before you open a pull request, check that:

- [ ] `ruff check .` passes.
- [ ] `pytest` passes.
- [ ] You updated the docs and README if behaviour changed.
- [ ] You added a line under `Unreleased` in [CHANGELOG.md](CHANGELOG.md).
- [ ] There are no real secrets in tests, logs or screenshots.

The pull request template will remind you of these. Thank you for contributing.
