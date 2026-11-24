# git_history_purge.py

Remove leaked secrets (passwords, API keys, tokens, connection strings) from **every commit** of a git repository, then replace the history on its remote (GitHub, GitLab, Azure DevOps, Bitbucket, or any git server).

- One Python file, no config file.
- Runs on Windows, macOS and Linux.
- Works on any repository; only the repository URL is required.
- Rehearses the push against a local copy before it touches your real remote.

---

## ⚠️ Read this before you start

### 1. Move your secrets to a secrets manager first

Purging git history only helps if the secrets **stop living in the code**. Before running this script:

1. Put every secret your applications still need into a secrets manager (see [Keeping secrets out of code](#keeping-secrets-out-of-code-the-secrets-manager-approach) for how it works and which services offer one).
2. Change the applications to read secrets from there, not from files committed to git.
3. Deploy and verify that every environment runs on the secrets manager.
4. Remove the secret values from the current code (`.env` files, config files, scripts) and add `.env*` to `.gitignore`.

Only then purge the history. The script **keeps** any value that is still in your current branch, because replacing it would break the running applications. If you skip this step, those secrets stay in git.

### 2. A purge is not a fix: rotate every secret

Once a secret has been pushed, treat it as leaked. After the purge, the old values still exist in:

- every developer's old clone and every fork,
- pull request pages on your hosting service (they keep the commits every PR ever pointed to),
- CI caches, build logs and backups.

**Rotate (change) every secret the script removes.** The purge keeps the history clean from now on; rotation makes the leaked values useless.

### 3. Everyone must re-clone

Every commit ID changes. Plan a short freeze, tell your team, and make sure nobody pushes from an old clone afterwards (see [After the purge](#after-the-purge-what-every-developer-does)).

---

## Keeping secrets out of code: the secrets manager approach

A secret written in code, a committed `.env` file or a config file is copied into every clone, fork, CI cache and backup, and it stays in git history forever. A secrets manager keeps the value in one central, access-controlled place. The application asks for it **at runtime**, so the repository only ever holds the secret's *name*, never its value.

### How it works

1. **Store** each secret once per environment under a clear name, for example `myapp/prod/DATABASE_PASSWORD`.
2. **Grant access by identity, not by password.** The app proves who it is with the platform's own identity (an AWS IAM role, an Azure managed identity, a GCP service account, a Kubernetes service account). No static credential is needed to fetch the secrets.
3. **Deliver the value at runtime**, in one of two ways:
   - *The app fetches it* with the provider's SDK at startup (and caches it in memory).
   - *The platform injects it* as environment variables or a mounted file just before the app starts (Kubernetes External Secrets Operator, the Secrets Store CSI driver, ECS/App Service/Cloud Run secret references, CI/CD secret variables). The app keeps reading `process.env`, but the value never touches the repository.
4. **Rotate** a secret by changing it in the manager and restarting (or reloading) the app. No code change, no commit.
5. **Audit**: every read and change is logged, so you can see who used which secret and when.

For local development, give each developer their own non-production values: an untracked `.env` (with `.env*` in `.gitignore` and a committed `.env.example` with empty values), or a CLI that pulls dev secrets on demand (`doppler run`, `infisical run`, `op run`, `aws secretsmanager get-secret-value`).

### Services that provide it

| Service | Type | Good fit when |
|---|---|---|
| AWS Secrets Manager | Cloud (AWS) | Apps run on AWS; built-in rotation for RDS and other AWS databases |
| AWS SSM Parameter Store (SecureString) | Cloud (AWS) | Cheaper AWS option for config plus a few secrets, no built-in rotation |
| Azure Key Vault | Cloud (Azure) | Apps run on Azure; also stores keys and certificates |
| Google Cloud Secret Manager | Cloud (GCP) | Apps run on GCP (Cloud Run, GKE, Cloud Functions) |
| HashiCorp Vault / OpenBao | Self-hosted or managed | Multi-cloud or on-premises; dynamic short-lived database credentials |
| Doppler | SaaS | One dashboard syncing secrets to many clouds, CI systems and local dev |
| Infisical | SaaS or self-hosted (open source) | Doppler-style workflow you can host yourself |
| 1Password Secrets Automation / Bitwarden Secrets Manager | SaaS | The team already uses that password manager |
| Akeyless, CyberArk Conjur | SaaS / enterprise | Enterprise compliance and centralised policy |
| GitHub Actions secrets, GitLab CI variables, Azure DevOps variable groups | CI/CD | Secrets needed only by the build and deploy pipeline |
| Kubernetes External Secrets Operator | Bridge | Syncs any of the managers above into Kubernetes `Secret` objects |
| SOPS, Sealed Secrets | Encrypted in git | You want secrets versioned in git, but only in encrypted form |

Plain Kubernetes `Secret` objects and CI variables are delivery mechanisms rather than full secrets managers: they are only base64-encoded or scoped to one pipeline. Pair them with one of the managers above for production.

---

## Install

You need Python 3.11+, git 2.45+, git-filter-repo and gitleaks 8.19+.

**macOS**

```
brew install python git git-filter-repo gitleaks
```

**Windows** (PowerShell)

```
winget install Python.Python.3.12 Git.Git gitleaks
```

```
pip install git-filter-repo
```

**Linux** (Debian/Ubuntu shown; use your package manager)

```
sudo apt install python3 python3-pip git
```

```
pip install git-filter-repo
```

Install gitleaks from its GitHub releases page: https://github.com/gitleaks/gitleaks/releases

Check everything is in place:

```
python3 --version && git --version && git filter-repo --version && gitleaks version
```

On Windows, use `python` instead of `python3` in every command on this page.

---

## Quick start

Replace `<repo-url>` with your repository URL (HTTPS, SSH or a local path).

**1. Dry run.** Safe, never changes your remote:

```
python3 git_history_purge.py test --repo-url <repo-url>
```

**2. Read the reports** in `purge-work/<repo-name>/reports/`. They list key names and value lengths only, never the values themselves.

**3. Real run.** Runs the dry run again, then asks you to type `PUSH`:

```
python3 git_history_purge.py all --repo-url <repo-url>
```

**4. Delete the local work copies.** They still contain the original secrets:

```
python3 git_history_purge.py cleanup --repo-url <repo-url>
```

See every option:

```
python3 git_history_purge.py --help
```

Use the **same `--repo-url` and options** for every command of one purge.

---

## Try it on a local copy first (recommended)

This runs the whole flow, push included, without touching your real remote:

```
git clone --mirror --ref-format=reftable <repo-url> local-copy.git
```

```
python3 git_history_purge.py all --repo-url local-copy.git
```

---

## What it does

| Step | What happens | Changes your remote? |
|---|---|---|
| `fetch` | Downloads every branch and tag. Drops read-only pull-request refs (`refs/pull/*`) | no |
| `find` | Finds every secret value: gitleaks over all history, every old version of `.env*` and `*-config.yml` files, and your extra patterns. Values still on your current branch are kept | no |
| `rewrite` | Rewrites a copy of the history with git-filter-repo: file contents and commit messages | no |
| `verify` | Checks: 0 secret values left, no branch or tag lost, current branch files byte-identical | no |
| `rehearse` | Pushes to a **local stand-in** with the real push code, clones it fresh and checks again | no |
| `push` | Force-pushes the current branch first, then all branches, then all tags. Asks you to type `PUSH` | **yes** |
| `cleanup` | Deletes the work folder. Asks you to type `DELETE` | no |
| `test` | `fetch` → `find` → `rewrite` → `verify` → `rehearse` | no |
| `all` | `test` + `push` | **yes** |

Each secret is replaced with a marker such as `[SECRET REMOVED FROM GIT 2026-11-18 18:14 UTC]`.

### Built-in safety

- `push` refuses unless `rehearse` passed for this exact rewritten copy.
- `push` refuses if the URL differs from the one `fetch` used, so a local test can never push to the real remote.
- `push` refuses if anyone pushed to the remote after `fetch`.
- The current branch is pushed first with `--force-with-lease`. If it's refused, nothing else is pushed.
- An interrupted or partly refused push resumes when you run `push` again.
- Before asking for `PUSH`, it lists open pull requests that will keep the old history reachable.

---

## Public keys in your repo: keeping or ignoring them

Some values in a repo are **public on purpose** and look like secrets to gitleaks: Stripe/Razorpay publishable keys, PostHog or Segment project keys, Google Analytics IDs, Sentry DSNs, Firebase web config. They ship to every browser anyway. They usually live in front-end config files such as `next.config.ts`, `vite.config.ts` or `src/config.js`.

The script handles them in two ways:

| Where the public value is | What the script does | Where in the script |
|---|---|---|
| Still in today's code (current branch) | **Kept automatically** in every commit, everywhere in history. Nothing to configure | `keep_values_still_on_reference_branch` (around line 520) |
| Only in old versions of a file | **Replaced**, unless you tell the script to ignore that file | `DEFAULT_GITLEAKS_IGNORED_FILES` (around line 43) or the `--gitleaks-ignored-files` option |

### Step by step

**Step 1. Make sure the value really is public.**
Check the vendor's documentation. A key is public only if it is *meant* to be shipped to browsers or mobile apps. Some examples:

| Public (safe in front-end code) | Secret (never in git) |
|---|---|
| Stripe `pk_live_...`, Razorpay `rzp_live_...` key id | Stripe `sk_live_...`, Razorpay key secret |
| PostHog `phc_...` project key | PostHog `phx_...` personal key |
| Sentry DSN | Sentry auth token `sntrys_...` |
| Google Analytics ID, Firebase web config | Firebase service-account JSON |

If you are not sure, treat it as a secret.

**Step 2. Run a dry run and see what the script found.**

```
python3 git_history_purge.py test --repo-url <repo-url>
```

Then open these reports in `purge-work/<repo-name>/reports/`:

- `gitleaks-findings.tsv`: every gitleaks finding, with rule, file, key name and decision (`included` means it will be replaced).
- `kept-values-still-on-reference-branch.txt`: values kept because they are still in today's code (lengths only, never the values).

**Step 3a. The public key is still in today's code: nothing to do.**
It is kept automatically. After the purge, gitleaks still reports it, because it is still in the code. That is expected; see Step 4.

**Step 3b. You also want OLD versions of a file left untouched.**
Only do this for files you are sure never held a real secret. Pick one way:

*Option 1 (recommended): pass the file on the command line.* Keep the default lock files and add your file, here `next.config.*`:

```
python3 git_history_purge.py test --repo-url <repo-url> --gitleaks-ignored-files "(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|next\.config\.(js|ts|mjs))$"
```

To ignore several files, add them inside the brackets, separated by `|`:

```
python3 git_history_purge.py test --repo-url <repo-url> --gitleaks-ignored-files "(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|next\.config\.(js|ts|mjs)|src/config/public\.ts)$"
```

Use exactly the same option again when you run `all`.

*Option 2: change the default in the script*, so you don't have to pass the option every time. Open `git_history_purge.py` and find this line (around line 43):

```
DEFAULT_GITLEAKS_IGNORED_FILES = r"(pnpm-lock\.yaml|package-lock\.json|yarn\.lock)$"
```

Add your file inside the brackets:

```
DEFAULT_GITLEAKS_IGNORED_FILES = r"(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|next\.config\.(js|ts|mjs))$"
```

Either way, run `test` again and check `gitleaks-findings.tsv`: that file's rows now say `ignored file`.

A value is still replaced if it is *also* found somewhere else, for example in a `.env` file, a `*-config.yml` file, or by an `--extra-secret-pattern`. That is on purpose: a value sitting in a `.env` file next to real secrets is treated as a secret.

**Step 4. Stop gitleaks flagging public keys in future scans (optional).**
The purge doesn't change how gitleaks scans your repo afterwards. Two ways to stop the noise:

- *Best:* move the public keys out of the code into build-time variables from your CI/CD (for example `NEXT_PUBLIC_*` set per environment) and read them with `process.env`.
- *Quick:* add a `.gitleaks.toml` at the root of the repo that allowlists the **exact** values, with a description saying why they are public:

```
[extend]
useDefault = true

[allowlist]
description = "Public keys that are meant to be shipped to browsers"
regexes = [
  '''rzp_live_PUT_THE_EXACT_VALUE_HERE''',
  '''phc_PUT_THE_EXACT_VALUE_HERE''',
]
```

Allowlist exact values only. Don't allowlist a whole prefix like `phc_` or a whole file: that could hide a real secret added later.

---

## Options

| Option | Meaning | Default |
|---|---|---|
| `--repo-url` | Repository to clean | required |
| `--reference-branch` | Branch whose current files must stay identical; values on it are kept | the remote's default branch |
| `--replacement-text` | Text that replaces each secret; `{timestamp}` is filled in | `[SECRET REMOVED FROM GIT {timestamp}]` |
| `--timezone-offset` / `--timezone-label` | Timezone of the timestamp, e.g. `+05:30` / `IST` | `+00:00` / `UTC` |
| `--remove-path` | Glob deleted from every commit, e.g. committed build output (repeatable) | none |
| `--extra-secret-pattern` | Regex searched in every diff (repeatable) | none |
| `--extra-literals-file` | File with one extra value to remove per line | none |
| `--min-secret-length` | Shorter values are skipped as too risky to replace everywhere | `8` |
| `--secret-key-pattern` | Regex for config keys that hold secrets | `PASSWORD`, `TOKEN`, `API_KEY`, `_KEY$`, ... |
| `--config-file-pattern` | Regex for config files read in every old version | `.env*`, `*-config.yml` |
| `--gitleaks-ignored-files` | Regex for files whose gitleaks findings are ignored | lock files |
| `--drop-ref-prefix` | Read-only refs dropped after download (repeatable) | `refs/pull/` |
| `--validation-file` / `--validation-config-dir` | Optional: stop if a secret key still used under the config folder is missing from the validation file | off |
| `--allow-unvalidated-keys` | Continue past that check anyway | off |
| `--full` | `verify` also re-runs gitleaks (slower) | off |
| `--work-dir` | Work folder | `./purge-work/<repo-name>` |

### Example with options

```
python3 git_history_purge.py all --full --repo-url https://github.com/your-org/your-repo.git --replacement-text "[SECRET REMOVED FROM GIT {timestamp} - NOW IN SECRETS MANAGER]" --remove-path "dist/*" --extra-secret-pattern "sk_live_[A-Za-z0-9]{20,}"
```

---

## Running the real purge

### Before

1. Secrets are in a secrets manager and the apps read them from there (see the warning at the top).
2. Make a backup of the remote. It contains the secrets, so keep it private and delete it once rotation is done:

   ```
   git clone --mirror --ref-format=reftable <repo-url> backup-before-purge.git
   ```

3. Run `test` and read the reports.
4. Tell the team: push every branch, merge or close open pull requests, then stop pushing.
5. Disable every CI/CD pipeline that deploys on push or tag; pushed tags could otherwise start deploys of old versions.
6. The account that pushes must be allowed to force-push to every branch, including protected ones:
   - **GitHub:** temporarily allow force pushes in branch protection or rulesets.
   - **GitLab:** temporarily unprotect the branches, or allow force push.
   - **Azure DevOps:** Contribute, Force push, and Bypass policies when pushing.

### Run

```
python3 git_history_purge.py all --full --repo-url <repo-url>
```

On a repository with ~9,000 commits this takes about 10–15 minutes before it asks for `PUSH`.

### After

1. Re-enable the pipelines and restore branch protection.
2. For a day, allow only yourself to push to the main branch, so nobody pushes from an old clone.
3. Tell the team to re-clone (see the next section).
4. **Rotate every removed secret.**
5. Run `cleanup`. Delete the backup once rotation is done.

---

## After the purge: what every developer does

> **Never run `git pull` or `git push` in an old clone.** A pull merges the old history (secrets included) back in, and a push sends it to the remote again.

Pushed everything before the freeze? Clone fresh and switch to your branch:

```
git clone <repo-url>
```

```
git checkout <your-branch>
```

Have commits that were never pushed? In the **old** clone:

```
git fetch
```

```
git format-patch origin/main..<your-branch> -o ~/my-patches
```

Then in the **new** clone:

```
git checkout -b <your-branch>
```

```
git am ~/my-patches/*.patch
```

Have uncommitted changes? In the old clone:

```
git diff > ~/wip.patch
```

In the new clone:

```
git apply ~/wip.patch
```

Had an open pull request? Close it, then open a new one from the same branch in the fresh clone.

Copy untracked files such as local `.env` files into the new clone by hand.

---

## What a purge cannot remove

- **Pull request history** on GitHub, GitLab, Azure DevOps and others. They keep every commit a PR ever pointed to, so old PR pages can still show old values. Only moving to a brand-new repository removes them.
- **Open pull-request refs** (`refs/pull/*`) at the time of the push.
- **Copies elsewhere:** old clones, forks, CI caches, logs, backups.

That's why rotating every removed secret is not optional.

---

## Troubleshooting

Every stop prints `[STOP]` with the reason. Nothing is pushed unless the push step says so.

| Message | What to do |
|---|---|
| `the remote changed since the fetch step` | Someone pushed. Run `all` again |
| `<branch> was refused` | Read **which account** the error names. git uses whatever login is saved for that host, which may not be the account you meant. Fix the login or the permission, then run `push` again; it resumes |
| `Authentication failed` | Most hosts reject account passwords for git. Use a personal access token with repository write access |
| `has not passed the rehearse step` | Run `test` first with the same `--repo-url` |
| `history was fetched from X but you are pushing to Y` | Use the same `--repo-url` for every command |
| `no secret values found` | Nothing to purge |
| `secret keys still live but not validated` | Add them to your validation file, or pass `--allow-unvalidated-keys` |
| A check failed in `verify` or `rehearse` | Don't push. Read the reports named in the message |

### Push with a specific token (this terminal window only)

Use this when git keeps using the wrong saved login.

**macOS / Linux:**

```
export GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0= GIT_CONFIG_KEY_1=credential.helper GIT_CONFIG_VALUE_1='!f() { echo username=token; echo "password=${PURGE_TOKEN}"; }; f'
```

```
read -s PURGE_TOKEN; export PURGE_TOKEN
```

**Windows PowerShell:**

```
$env:GIT_CONFIG_COUNT="2"; $env:GIT_CONFIG_KEY_0="credential.helper"; $env:GIT_CONFIG_VALUE_0=""; $env:GIT_CONFIG_KEY_1="credential.helper"; $env:GIT_CONFIG_VALUE_1='!f() { echo username=token; echo "password=${PURGE_TOKEN}"; }; f'
```

```
$env:PURGE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR((Read-Host -AsSecureString "Token")))
```

Close the window and revoke the token when you're done.

---

## Rolling back

If something goes wrong after the push, restore every branch and tag from your backup:

```
cd backup-before-purge.git
```

```
git push --force <repo-url> "refs/heads/*:refs/heads/*" "refs/tags/*:refs/tags/*"
```

---

## Preventing the next leak

- Keep secrets only in a secrets manager; commit a `.env.example` with empty values instead of `.env`.
- Add a gitleaks check to your pull-request pipeline, so a secret is caught before it is merged.
- Turn on your host's push protection or secret scanning if it has one.
- Treat any secret that reached git as leaked: rotate it right away, even if you delete the commit.
