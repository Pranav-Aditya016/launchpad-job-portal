"""Boundary enforcement: LaunchPad never submits an application.

Spec §2 and §6.5. The agent prepares an application completely and stops; a human
presses submit. This test exists because a boundary that lives only in a design
document erodes. If this fails, do not weaken the test — remove the code.
"""

import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

# A string that names a submit control. Applied only to string LITERALS that
# reach a click, never to prose.
SUBMITISH = re.compile(r"(type=[\"']?submit|button\[type|apply-now|\bsubmit\b)", re.I)

# Identifiers that name a submit routine. Applied only to DECLARED names and
# attribute accesses, never to comments or docstrings.
SUBMIT_NAMES = re.compile(r"^(auto_?submit|submit_application|click_submit|do_apply)$", re.I)

# The methods that actually actuate a control.
ACTUATORS = {"click", "press", "dispatch_event", "tap"}


def _string_constants(node: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _submit_offenders(tree: ast.AST) -> list[tuple[str, int]]:
    """Automated-submission intent, found structurally rather than textually.

    An AST walk, for the same reason the credential check is one: a regex over
    raw source cannot tell code from prose. The previous regex version flagged
    `app/browser/__init__.py` because its DOCSTRING mentioned this test's own
    filename — "test_no_autosubmit.py" contains "autosubmit". A guard that cries
    wolf at documentation is a guard people delete.

    Two shapes are caught:
      1. an actuator call (`.click()`, `.press()`, …) where a submit-naming
         string literal appears in its arguments OR anywhere in the receiver
         chain — so `page.get_by_role("button", name="Submit").click()` and
         `page.locator("button[type=submit]").click()` are both caught, not just
         the direct `page.click("…submit…")` form;
      2. a declared or accessed identifier that names a submit routine.
    """
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ACTUATORS:
                haystack = _string_constants(node.func.value)
                for a in node.args:
                    haystack += _string_constants(a)
                for kw in node.keywords:
                    haystack += _string_constants(kw.value)
                for s in haystack:
                    if SUBMITISH.search(s):
                        out.append((f"{node.func.attr}(...{s[:40]}...)", node.lineno))
                        break
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif isinstance(node, ast.Name):
            name = node.id
        if name and SUBMIT_NAMES.match(name):
            out.append((name, node.lineno))
    return out


def test_no_submit_automation_anywhere_in_the_backend():
    offenders = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for what, line in _submit_offenders(tree):
            offenders.append(f"{path.relative_to(APP.parent)}:{line}: {what!r}")
    assert not offenders, (
        "Automated submission code detected — this violates a hard product "
        "boundary (spec §2). Remove it; do not relax this test.\n  "
        + "\n  ".join(offenders)
    )


def test_the_submit_guard_catches_real_violations_but_not_prose():
    """A guard never checked against a real violation is not a guard — and one
    that fires on documentation gets deleted by the next frustrated engineer."""
    caught = [
        'async def f(page):\n    await page.click("button[type=submit]")\n',
        'async def f(page):\n    await page.locator("button[type=submit]").click()\n',
        'async def f(page):\n    await page.get_by_role("button", name="Submit").click()\n',
        'def submit_application(page):\n    pass\n',
        'async def f(page):\n    sel = "x"\n    await page.click("input.apply-now")\n',
    ]
    for src in caught:
        assert _submit_offenders(ast.parse(src)), f"guard MISSED a violation:\n{src}"

    ignored = [
        # the exact false positive that broke the build
        '"""See backend/tests/test_no_autosubmit.py for the boundary."""\n',
        '# we never auto_submit anything\nx = 1\n',
        'def f(page):\n    """Never clicks submit."""\n    page.click("#cookie-accept")\n',
        'STATE = "submitted"   # the USER told us they submitted\n',
        'def mark_submitted(job_id):\n    pass\n',
    ]
    for src in ignored:
        assert not _submit_offenders(ast.parse(src)), f"guard FALSE-POSITIVED on:\n{src}"


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
