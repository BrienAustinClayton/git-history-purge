"""Terminal output and the typed confirmations (PUSH, DELETE) that guard every destructive step."""

class StepFailed(Exception):
    pass


def say(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def ok(message: str) -> None:
    print(f"  [ok]   {message}", flush=True)


def info(message: str) -> None:
    print(f"  [info] {message}", flush=True)


def fail(message: str) -> None:
    raise StepFailed(message)


def require_typed_word(prompt: str, word: str) -> None:
    answer = input(f"{prompt} Type {word} to continue: ").strip()
    if answer != word:
        fail("not confirmed. Nothing was changed.")
