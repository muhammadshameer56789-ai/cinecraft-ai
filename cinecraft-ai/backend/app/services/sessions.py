import re
import secrets

_RE = re.compile(r"^[0-9a-f]{32}$")


def new_session_id() -> str:
    return secrets.token_hex(16)


def valid_session(s) -> bool:
    return isinstance(s, str) and bool(_RE.match(s))
