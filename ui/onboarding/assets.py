"""Trusted local artwork only; crop without rewriting the original raster."""

from base64 import b64encode
from pathlib import Path


ASSETS = Path(__file__).parent / "frontend" / "assets"


def sphere_markup() -> str:
    """Clip the 786px central sphere out of the original 1360×1456 artwork."""
    texture = b64encode((ASSETS / "orange_app_icon.jpg").read_bytes()).decode("ascii")
    # A nested SVG viewport plus CSS circle clip avoids cross-shadow SVG ID lookup.
    return (
        '<svg class="sphere-art" xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 786 786" aria-hidden="true" focusable="false" '
        'style="border-radius:50%;clip-path:circle(49.75% at 50% 50%);overflow:hidden">'
        '<image x="-314" y="-356" width="1360" height="1456" '
        f'href="data:image/jpeg;base64,{texture}"/></svg>'
    )


def leaf_markup() -> str:
    """Return the independent vector core, never part of the sphere texture."""
    return (ASSETS / "orange_leaf.svg").read_text(encoding="utf-8")
