"""Guards on the Plotly contract our chart styling and config depend on.

The viewer restyles Plotly's modebar (active-tool highlight, a delayed tooltip)
and swaps in a custom snapshot button. That styling reaches into Plotly's own
class names and attributes — `.modebar-btn`, the `[data-title]` tooltip, the
`active` class, `Plotly.Icons.camera` — none of which are a stable public API.
A Plotly upgrade that renames any of them would break our CSS or JS silently:
the page still renders, but the tooltip never delays, the active tool stops
highlighting, or the snapshot button loses its icon.

These tests fail loudly when the vendored bundle stops shipping a token we rely
on, so the coupled rule can be updated in the same change as the upgrade. The
vendored file is found by glob, so bumping the Plotly version re-runs the check
against the new bundle automatically.
"""

from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_STATIC = _ROOT / "viewer" / "static"
_PARTIALS = _ROOT / "viewer" / "templates" / "partials"


def _plotly_bundle() -> str:
    matches = sorted(_STATIC.glob("vendor/plotly-*.min.js"))
    assert matches, "vendored Plotly bundle not found under viewer/static/vendor/"
    # If a future upgrade vendors more than one, check them all (join the text).
    return "\n".join(p.read_text() for p in matches)


# Each row: capability we depend on -> (tokens Plotly must still ship, the rule
# in our code that breaks if the token disappears). The message names the file
# and rule to fix, so a failure reads as a to-do, not a mystery.
_VENDOR_CONTRACT = {
    "modebar button class": (
        ["modebar-btn"],
        "style.css '.modebar-btn' rules and scripts_common.html querySelector('.modebar-btn')",
    ),
    "data-title tooltip": (
        ["[data-title]:hover:before", "content:attr(data-title)"],
        "style.css tooltip-delay override on '.modebar-btn[data-title]:hover:before/:after'",
    ),
    "active-tool state + inline fill": (
        ["setStyleOnHover", ".icon path", "activecolor"],
        "style.css '.modebar-btn.active' highlight; Plotly's inline active fill is why "
        "the icon-fill rule carries !important",
    ),
    "camera icon": (
        ["camera:{"],
        "scripts_common.html snapshot button uses Plotly.Icons.camera",
    ),
    "displaylogo config": (
        ["displaylogo"],
        "scripts_common.html plotConfig() sets displaylogo:false",
    ),
}


@pytest.mark.parametrize("capability,spec", _VENDOR_CONTRACT.items(), ids=list(_VENDOR_CONTRACT))
def test_vendored_plotly_still_ships_the_tokens_we_style(capability, spec):
    tokens, dependent_rule = spec
    bundle = _plotly_bundle()
    missing = [t for t in tokens if t not in bundle]
    assert not missing, (
        f"Vendored Plotly no longer ships {missing} for '{capability}'. "
        f"A Plotly upgrade likely renamed it; update: {dependent_rule}."
    )


def test_our_css_still_couples_to_the_plotly_modebar():
    # If someone drops these overrides, the drift guard above is styling nothing;
    # keep the coupling visible so the two move together.
    css = (_STATIC / "style.css").read_text()
    for needle in (".modebar-btn.active", "[data-title]:hover", "!important"):
        assert needle in css, f"style.css lost its Plotly modebar override: {needle!r}"


def test_our_plot_config_still_uses_the_plotly_hooks():
    js = (_PARTIALS / "scripts_common.html").read_text()
    for needle in ("Plotly.Icons.camera", "displaylogo", "modeBarButtons"):
        assert needle in js, f"scripts_common.html lost a Plotly config hook: {needle!r}"
