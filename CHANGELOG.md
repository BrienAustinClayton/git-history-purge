# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-11-24

### Changed

- Split the code into a `git_history_purge` package with one module per step and per detection concern.

### Added

- `git-history-purge` command, installable with pip or pipx.
- `--version` option.
- `pyproject.toml` packaging.
- Test suite.
- CI on Windows, macOS and Linux.
- Community files: license, contributing guide, code of conduct, security policy, issue forms, pull request template and architecture guide.

## [1.0.0] - 2026-11-24

### Added

- Initial single-file release with the `fetch`, `find`, `rewrite`, `verify`, `rehearse`, `push` and `cleanup` steps.
- Secret detection with gitleaks and every old version of config files.
- Reference-branch value protection, so values still used in today's code are kept.
- Push rehearsal and safety gates before anything touches the real remote.
- Language-agnostic defaults for config files and lock files.

[Unreleased]: https://github.com/BrienAustinClayton/remove-secrets-from-git-history/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/BrienAustinClayton/remove-secrets-from-git-history/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/BrienAustinClayton/remove-secrets-from-git-history/releases/tag/v1.0.0
