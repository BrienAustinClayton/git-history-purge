"""The seven purge steps in order, and the combined runs (test, all) built from them."""

from git_history_purge.steps.cleanup import step_cleanup
from git_history_purge.steps.fetch import step_fetch
from git_history_purge.steps.find import step_find
from git_history_purge.steps.push import step_push
from git_history_purge.steps.rehearse import step_rehearse
from git_history_purge.steps.rewrite import step_rewrite
from git_history_purge.steps.verify import step_verify

STEPS = {
    "fetch": (step_fetch, "Download every branch and tag into the work folder"),
    "find": (step_find, "Find every secret value in history (gitleaks + old config files + extra patterns)"),
    "rewrite": (step_rewrite, "Rewrite a copy of the history: every secret becomes the replacement text"),
    "verify": (step_verify, "Check the copy: 0 secrets left, no branch/tag lost, reference branch files unchanged"),
    "rehearse": (step_rehearse, "Push to a LOCAL stand-in with the real push code, re-clone it and check again"),
    "push": (step_push, "FORCE-PUSH to the real remote (only after a passed rehearsal; asks you to type PUSH)"),
    "cleanup": (step_cleanup, "Delete the work folder (asks you to type DELETE)"),
}
COMBINED_STEPS = {
    "test": ["fetch", "find", "rewrite", "verify", "rehearse"],
    "all": ["fetch", "find", "rewrite", "verify", "rehearse", "push"],
}
