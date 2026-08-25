"""Boundary enforcement: LaunchPad never submits an application.

Spec §2 and §6.5. The agent prepares an application completely and stops; a human
presses submit. This test exists because a boundary that lives only in a design
document erodes. If this fails, do not weaken the test — remove the code.
"""

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# Patterns that would indicate automated submission. Written to catch intent
# (a click aimed at a submit control) rather than every possible `.click()`,
# which has legitimate uses like dismissing a cookie banner.
FORBIDDEN = [
    re.compile(r"""click\(\s*['"][^'"]*submit""", re.I),
    re.compile(r"""click\(\s*['"][^'"]*apply-now""", re.I),
    re.compile(r"""(auto_?submit|submit_application|click_submit|do_apply)""", re.I),
    re.compile(r"""get_by_role\(\s*['"]button['"][^)]*name\s*=\s*['"][^'"]*submit""", re.I),
    re.compile(r"""press\(\s*['"]Enter['"]\s*\)\s*#\s*submit""", re.I),
]


def test_no_submit_automation_anywhere_in_the_backend():
    offenders = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN:
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(APP.parent)}:{line}: {match.group(0)!r}")
    assert not offenders, (
        "Automated submission code detected — this violates a hard product "
        "boundary (spec §2). Remove it; do not relax this test.\n  "
        + "\n  ".join(offenders)
    )


def _credential_identifiers(tree: ast.AST) -> list[tuple[str, int]]:
    """Every place this module DECLARES a name, with its line number.

    An AST walk rather than a regex: the boundary we are protecting is about
    fields and parameters, and a regex over source text cannot tell a field
    declaration from a docstring that happens to wrap onto a line starting
    "password:" — which the Connection docstring legitimately does.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.append((node.target.id, node.lineno))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    found.append((t.id, t.lineno))
        elif isinstance(node, ast.arg):
            found.append((node.arg, node.lineno))
        elif isinstance(node, ast.keyword) and node.arg:
            found.append((node.arg, node.lineno))
    return found


FORBIDDEN_NAMES = {
    "password", "passwd", "pwd", "otp", "one_time_password",
    "security_answer", "secret_answer", "username",
}


def test_no_credential_fields_in_any_model_or_router():
    """No model field, function parameter or keyword argument may be a credential.

    LaunchPad never sees the user's password: they log into each portal
    themselves in a real browser window, and only the resulting browser
    session is persisted locally (spec §2, §6.3).
    """
    offenders = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for name, lineno in _credential_identifiers(tree):
            if name.lower() in FORBIDDEN_NAMES:
                offenders.append(f"{path.relative_to(APP.parent)}:{lineno}: {name}")
    assert not offenders, (
        "A credential identifier was declared — LaunchPad never stores "
        "credentials (spec §2, §6.3).\n  " + "\n  ".join(offenders)
    )
