"""Guards on the HTML templates that a Python unit test can enforce.

These catch template regressions that wouldn't fail any Python path but would
break the rendered page.
"""

import re
from pathlib import Path

TEMPLATES = Path(__file__).parent.parent / "viewer" / "templates"
PARTIALS = TEMPLATES / "partials"

# A bare browser dialog call: window.confirm/alert/prompt, or the same built-ins
# called plain. Lowercase and not preceded by a word char, so the button text
# "Confirm", the class "confirm-ok", and the attribute "hx-confirm" don't match.
_BARE_DIALOG = re.compile(r"(?<![\w-])(?:window\.)?(?:alert|confirm|prompt)\s*\(")


def test_every_topbar_stats_oob_swap_keeps_its_class():
    """An hx-swap-oob replacement of #topbar-stats must carry class="topbar-stats".

    htmx's outerHTML OOB swap replaces the whole element, so a replacement that
    omits the class strips `.topbar-stats` off the live element, collapsing the
    header's flex row into a vertical stack. Every OOB copy must repeat the
    class that the canonical element in topbar.html declares.
    """
    offenders = []
    for path in PARTIALS.glob("*.html"):
        text = path.read_text()
        for m in re.finditer(r'<div id="topbar-stats"[^>]*>', text):
            tag = m.group(0)
            if "hx-swap-oob" in tag and 'class="topbar-stats"' not in tag:
                offenders.append(f"{path.name}: {tag}")
    assert not offenders, "OOB #topbar-stats swap missing the class:\n" + "\n".join(offenders)


def test_no_bare_browser_dialogs_in_templates():
    """Confirmations and notices use the in-app dialog, not window.confirm/alert/prompt.

    htmx's hx-confirm is allowed: scripts_common.html intercepts htmx:confirm and
    drives an in-app modal. What's banned is a raw browser popup, which can't be
    themed and reads as foreign next to the app's own UI.
    """
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        if "vendor" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if _BARE_DIALOG.search(line):
                offenders.append(f"{path.relative_to(TEMPLATES)}:{lineno}: {line.strip()}")
    assert not offenders, "bare browser dialog call(s) — route through the in-app dialog:\n" + "\n".join(offenders)


def test_htmx_confirm_is_intercepted_for_the_in_app_dialog():
    """The hx-confirm interceptor must stay wired, or htmx falls back to window.confirm."""
    js = (PARTIALS / "scripts_common.html").read_text()
    assert "htmx:confirm" in js, "lost the htmx:confirm listener that drives the in-app dialog"
    assert "issueRequest" in js, "in-app confirm no longer proceeds the htmx request"
