"""Default patterns, replacement text and push checklists. Every default can be overridden on the command line."""

MINIMUM_GIT_VERSION = (2, 45)
DEFAULT_SECRET_KEY_PATTERN = (
    r"(SECRET(_KEY)?$|PASSWORD|PASSWD|(^|_)TOKEN($|_)|API_KEY|APIKEY|PRIVATE_KEY|ACCESS_KEY"
    r"|KEY_ID|CLIENT_ID|DSN$|DATABASE_URL|_KEY$|[a-z](Key|Token|Secret)$)"
)
DEFAULT_CONFIG_FILE_PATTERN = (
    r"(^|/)(\.env[^/]*|[^/]*\.env|[^/]*\.(properties|ini|cfg|conf|tfvars)"
    r"|[^/]*(config|secret|setting|application|credential|values|compose)[^/]*\.ya?ml)$"
)
DEFAULT_GITLEAKS_IGNORED_FILES = (
    r"(^|/)(pnpm-lock\.yaml|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|bun\.lockb?|Cargo\.lock"
    r"|Gemfile\.lock|poetry\.lock|Pipfile\.lock|uv\.lock|composer\.lock|go\.sum|packages\.lock\.json"
    r"|gradle\.lockfile|pubspec\.lock|Podfile\.lock|mix\.lock)$"
)
DEFAULT_VALIDATION_KEY_PATTERN = r"\b([A-Z][A-Z0-9_]*[A-Z0-9])\b"
DEFAULT_REPLACEMENT = "[SECRET REMOVED FROM GIT {timestamp}]"
DEFAULT_BEFORE_PUSH_CHECKLIST = [
    "Every secret the apps still need lives in a secrets manager (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault, ...) and the apps read it from there",
    "CI/CD pipelines that deploy on push or tag are DISABLED",
    "The team was told to stop pushing",
    "Open pull requests are completed or abandoned",
    "The account you push with may force-push to every branch, including protected ones",
]
DEFAULT_AFTER_PUSH_CHECKLIST = [
    "Re-enable the pipelines",
    "Everyone deletes their old clone and re-clones (never pull or push from an old clone)",
    "Rotate every removed secret",
    "Run the cleanup step",
]
