import posixpath
import re
import shlex

SAFE_PREFIXES = ("pwd", "ls", "python --version", "head -n", "rg")
SHELL_SYNTAX = "\n\r\x00$`;&|<>()#"


def tokens(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def relative_path(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or value.startswith(("/", "-", "~"))
        or ".." in value.split("/")
        or any(ord(c) < 32 for c in value)
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError("Use a bounded relative sandbox path without traversal.")
    return value


def destructive_reasons(command):
    if not isinstance(command, str):
        return []
    if len(command) > 1024:
        return ["oversized unclassified command"]
    try:
        words = tokens(command)
    except ValueError:
        words = re.findall(r"[^\s'\";|&<>]+|[<>]+", command)
    try:
        if not any(c in command for c in SHELL_SYNTAX) and safe_arguments(words):
            # In this complete read-only grammar, operands are literal data.
            words = words[:1]
    except ValueError:
        pass
    names = [posixpath.basename(w).lower() for w in words]
    reasons = []
    if "rm" in names and any(
        w == "--recursive"
        or w.startswith("--recursive=")
        or (w.startswith("-") and not w.startswith("--") and "r" in w.lower())
        for w in words
    ):
        reasons.append("recursive deletion")
    if {"sudo", "su", "doas", "pkexec"} & set(names):
        reasons.append("privilege escalation")
    if {"chmod", "chown", "chgrp", "chflags", "setfacl"} & set(names):
        reasons.append("permission or ownership change")
    if any(w.startswith("of=/dev/") for w in words) or (
        {"dd", "cp", "mv", "tee", "cat"} & set(names)
        and any(w.startswith("/dev/") for w in words[1:])
    ):
        reasons.append("raw-device write")
    if any(n == "mkfs" or n.startswith("mkfs.") or n in {"newfs", "mke2fs"} for n in names):
        reasons.append("filesystem creation")
    if any(
        ">" in word and index + 1 < len(words) and words[index + 1].startswith("/")
        for index, word in enumerate(words)
    ):
        reasons.append("root-path redirection")
    return reasons


def is_destructive(command):
    return bool(destructive_reasons(command))


def safe_arguments(words):
    if words in (["pwd"], ["ls"], ["python", "--version"]):
        return True
    if len(words) == 4 and words[:2] == ["head", "-n"]:
        if not re.fullmatch(r"[1-9][0-9]{0,2}", words[2]) or int(words[2]) > 200:
            return False
        relative_path(words[3])
        return True
    if len(words) == 5 and words[0] == "rg" and words[2] == "--glob" and words[4] == ".":
        if not words[1] or len(words[1]) > 128 or words[1].startswith("-"):
            return False
        relative_path(words[3])
        return True
    return False


def confirm_bash(command, auto_approve=False, *, confirmed_command=None):
    """Confirmation is a trusted-Python-only exact command, never a model argument.

    Callers may supply confirmed_command only after explicit human confirmation.
    FileTools.bash exposes no such parameter and executes only the safe grammar.
    """
    reasons = destructive_reasons(command)
    result = {"allowed": False, "destructive": bool(reasons), "reason": ""}
    if reasons and confirmed_command != command:
        return {
            **result,
            "reason": "; ".join(reasons) + "; explicit command-specific confirmation required.",
        }
    if (
        not isinstance(command, str)
        or not command.strip()
        or len(command) > 1024
        or any(c in command for c in SHELL_SYNTAX)
    ):
        return {
            **result,
            "reason": "Unsupported shell syntax, substitution, redirection or length.",
        }
    try:
        words = tokens(command)
        if reasons:
            return {
                **result,
                "allowed": True,
                "reason": "Explicit confirmation matches this exact destructive command.",
            }
        prefix_match = any(words[: len(tokens(p))] == tokens(p) for p in SAFE_PREFIXES)
        allowed = prefix_match and safe_arguments(words)
    except ValueError:
        return {**result, "reason": "Invalid quoting or sandbox path."}
    return {
        **result,
        "allowed": bool(allowed),
        "reason": (
            "Allowed exact read-only grammar" + (" (auto-approved)." if auto_approve else ".")
        )
        if allowed
        else "Command or arguments are outside the supported read-only grammar.",
    }
