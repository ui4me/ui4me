"""Theme stylesheet loading. The CSS is plain text shipped in ``assets/theme.css``."""
from __future__ import annotations

from functools import lru_cache
from importlib import resources

THEMES = ("system", "light", "dark")


@lru_cache(maxsize=1)
def theme_css() -> str:
    return resources.files("ui4me._ui").joinpath("assets/theme.css").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def functional_css() -> str:
    """Structural invariants retained when a user replaces all visual styling."""
    return resources.files("ui4me._ui").joinpath("assets/functional.css").read_text(encoding="utf-8")


# Named visual presets are plain CSS layered on the same semantic tokens.
# Applications can still replace the stylesheet completely with Theme.load().
PRESET_TOKENS: dict[str, tuple[str, str, str, str]] = {
    "default": ("#2563eb", "#5b8cff", "#f4f6fa", "#0f141b"),
    "ocean": ("#087eac", "#49b8e8", "#f0f7fa", "#101d27"),
    "sage": ("#527a53", "#86c68c", "#f3f7f1", "#121c16"),
    "violet": ("#7654c4", "#ac8dff", "#f7f4fd", "#191422"),
    "graphite": ("#4d617d", "#a1b0c4", "#f1f3f6", "#12171e"),
}

def preset_css(name: str) -> str:
    if name not in PRESET_TOKENS:
        raise ValueError(f"unknown theme preset {name!r}; choose {', '.join(PRESET_TOKENS)}")
    if name == "default":
        return theme_css()
    light, dark, light_bg, dark_bg = PRESET_TOKENS[name]
    return (theme_css() + f"\n/* UI4ME preset: {name} */\n"
            + f":root {{ --u4-primary:{light}; --u4-focus:{light}; --u4-bg:{light_bg}; }}\n"
            + f"@media(prefers-color-scheme:dark) {{ :root {{ --u4-primary:{dark}; --u4-focus:{dark}; --u4-bg:{dark_bg}; }} }}\n")
