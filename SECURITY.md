# Security Policy

This tool handles leaked secrets and rewrites git history, so we take security reports seriously. Thank you for helping keep it safe.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.x     | Yes       |
| below 1.0 | No      |

## Report a security vulnerability

Please report vulnerabilities privately. Do not open a public issue.

1. Open the [Security tab](https://github.com/BrienAustinClayton/remove-secrets-from-git-history/security) of this repository.
2. Click **Report a vulnerability** (GitHub private vulnerability reporting).
3. Fill in the form and send it.

Only the maintainer can see your report.

### What to include

- A short description of the problem and why it matters.
- The step involved (`fetch`, `find`, `rewrite`, `verify`, `rehearse`, `push` or `cleanup`).
- Steps to reproduce, ideally with a throwaway test repository.
- Your `git-history-purge --version`, operating system, and git, git-filter-repo and gitleaks versions.
- Any fix ideas you have (optional).

> [!CAUTION]
> Never paste real secrets, report files from `purge-work/`, or secret values into issues, pull requests or vulnerability reports. Use fake values such as `FAKE_TOKEN_123` instead. If a real secret slips into a report, revoke it right away.

### What to expect

We aim to respond within a week. We will tell you whether we can reproduce the problem, and we will keep you updated while we work on a fix. We are happy to credit you in the release notes if you would like that.

## Security design

These safeguards are built in so a run cannot easily hurt your real repository or leak more secrets:

- **Rehearsal gate.** `push` refuses to run until `rehearse` has passed for this exact cleaned copy.
- **URL and remote-changed checks.** `push` checks that the URL matches the one used by `fetch`, and that nobody pushed to the remote since `fetch`.
- **Safe force-push.** The reference branch goes first with `--force-with-lease`, then other branches, then tags.
- **Typed confirmation.** `push` needs you to type `PUSH`, and `cleanup` needs you to type `DELETE`.
- **Reports hold lengths only.** Find reports list key names and value lengths, never the values themselves.
- **Private work folder.** Folders holding secrets are created with `0700` permissions.
- **Cleanup deletes the originals.** The `cleanup` step removes the work folder that holds the original secrets.
