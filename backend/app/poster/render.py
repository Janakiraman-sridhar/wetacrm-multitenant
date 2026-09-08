"""Rendering a poster from its layer spec.

**One renderer, used everywhere** — the editor preview, the batch output, and
whatever gets sent over WhatsApp all come through here. A separate client-side
preview would drift the first time a font fell back or a line wrapped differently,
and the agent would only find out from the customer.

A layer is one of:

```jsonc
{"type": "rect",  "x": 0, "y": 0, "w": 1080, "h": 300, "fill": "#4F46E5", "radius": 0, "opacity": 1}
// any layer may declare `"requires": "agent_mobile"` (or a list) and is skipped when
// that merge field is empty — how a button's background disappears with its label
{"type": "text",  "x": 60, "y": 120, "w": 960, "text": "Happy birthday {customer_name}!",
                  "size": 64, "color": "#FFFFFF", "align": "center", "bold": true,
                  "line_height": 1.2, "max_lines": 3, "italic": false, "font": "sans",
                  "opacity": 1, "letter_spacing": 0, "uppercase": false,
                  "shadow": {"color": "#00000080", "dx": 2, "dy": 2},
                  "outline": {"color": "#000000", "width": 2}}
{"type": "image", "x": 60, "y": 700, "w": 240, "h": 240, "source": "logo|agent_photo|asset",
                  "asset_key": "...", "radius": 0, "fit": "cover", "opacity": 1}
{"type": "line",  "x": 60, "y": 400, "w": 960, "h": 4, "fill": "#FFFFFF", "opacity": 1}
// The background may be a flat colour, a gradient between two, or an image with a
// scrim: {"color": "#fff", "gradient": {"to": "#4F46E5", "angle": "vertical"},
//         "image": "...", "overlay": "#00000059"}
```

Coordinates are in pixels against the template's canvas size, top-left origin.
"""

import io
import logging
import os
import re
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.poster.models import POSTER_SIZES

log = logging.getLogger("weta.poster")

#: Candidate font files, in order. The bundled Linux paths matter for Docker; the
#: Windows ones for local dev. Pillow's bitmap default is the last resort and looks
#: it, so a missing font is logged rather than silently accepted.
#: Font families offered in the editor, each as a candidate list: bundled Linux
#: paths first for Docker, then macOS, then Windows for local dev. A family that
#: resolves to nothing falls back to `sans` rather than to Pillow's bitmap default,
#: which looks like a ransom note next to real type.
_FONT_FAMILIES: dict[str, dict[str, list[str]]] = {
    "sans": {
        "regular": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/Library/Fonts/Arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ],
        "bold": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ],
        "italic": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            "C:/Windows/Fonts/ariali.ttf",
        ],
        "bolditalic": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
            "C:/Windows/Fonts/arialbi.ttf",
        ],
    },
    "serif": {
        "regular": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/Library/Fonts/Times New Roman.ttf",
            "C:/Windows/Fonts/times.ttf",
            "C:/Windows/Fonts/georgia.ttf",
        ],
        "bold": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
            "C:/Windows/Fonts/timesbd.ttf",
            "C:/Windows/Fonts/georgiab.ttf",
        ],
        "italic": [
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
            "C:/Windows/Fonts/timesi.ttf",
        ],
        "bolditalic": [
            "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
            "C:/Windows/Fonts/timesbi.ttf",
        ],
    },
    "mono": {
        "regular": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
            "C:/Windows/Fonts/consola.ttf",
            "C:/Windows/Fonts/cour.ttf",
        ],
        "bold": [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
            "C:/Windows/Fonts/consolab.ttf",
            "C:/Windows/Fonts/courbd.ttf",
        ],
        "italic": ["C:/Windows/Fonts/consolai.ttf"],
        "bolditalic": ["C:/Windows/Fonts/consolaz.ttf"],
    },
}

FONT_FAMILIES = list(_FONT_FAMILIES)

_font_cache: dict[tuple[str, str, int], Any] = {}
_warned = False


def _weight_key(bold: bool, italic: bool) -> str:
    if bold and italic:
        return "bolditalic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "regular"


def load_font(size: int, bold: bool = False, family: str = "sans", italic: bool = False):
    """A font file for this family and weight, falling back rather than failing.

    Falls back along two axes before giving up: an unavailable italic drops to the
    upright of the same family, and an unavailable family drops to `sans` — a poster
    set in the wrong weight is a small disappointment, one set in Pillow's bitmap
    default is unusable.
    """
    global _warned
    family = family if family in _FONT_FAMILIES else "sans"
    weight = _weight_key(bold, italic)
    key = (family, weight, size)
    if key in _font_cache:
        return _font_cache[key]

    candidates = list(_FONT_FAMILIES[family].get(weight) or [])
    if weight in ("italic", "bolditalic"):
        candidates += _FONT_FAMILIES[family].get("bold" if bold else "regular") or []
    if family != "sans":
        candidates += _FONT_FAMILIES["sans"].get(weight) or []
        candidates += _FONT_FAMILIES["sans"]["regular"]

    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _font_cache[key] = font
                return font
            except Exception:
                continue

    if not _warned:
        log.warning(
            "No TrueType font found — posters will render with Pillow's bitmap default. "
            "Install fonts-dejavu-core in the image to fix this."
        )
        _warned = True
    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _colour(value: str | None, fallback=(0, 0, 0, 255)):
    if not value:
        return fallback
    text = str(value).strip().lstrip("#")
    try:
        if len(text) == 3:
            text = "".join(c * 2 for c in text)
        if len(text) == 6:
            return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
        if len(text) == 8:
            return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4, 6))
    except ValueError:
        pass
    return fallback


def _opacity_factor(opacity) -> float:
    """Coerce a layer's `opacity` to 0–1, treating anything unusable as opaque."""
    if opacity is None:
        return 1.0
    try:
        return max(0.0, min(1.0, float(opacity)))
    except (TypeError, ValueError):
        return 1.0


def _with_opacity(colour, opacity) -> tuple:
    """Apply a 0–1 opacity to an RGBA tuple, leaving it alone when unset."""
    return colour[:3] + (int(colour[3] * _opacity_factor(opacity)),)


def _gradient(width: int, height: int, start, end, angle: str = "vertical") -> Image.Image:
    """A two-stop linear gradient.

    Drawn one line at a time rather than with numpy: the dependency is not worth it
    for an image this size, and a 1080px poster costs about a millisecond.
    """
    base = Image.new("RGBA", (width, height), start)
    draw = ImageDraw.Draw(base)
    horizontal = angle == "horizontal"
    steps = width if horizontal else height
    for i in range(steps):
        ratio = i / max(1, steps - 1)
        colour = tuple(
            int(start[c] + (end[c] - start[c]) * ratio) for c in range(4)
        )
        if horizontal:
            draw.line([(i, 0), (i, height)], fill=colour)
        else:
            draw.line([(0, i), (width, i)], fill=colour)
    return base


MERGE_PATTERN = re.compile(r"\{([a-z_]+)\}")


def apply_merge(text: str, values: dict) -> str:
    """Replace `{field}` placeholders.

    An unknown field is emptied rather than left as `{oops}`, because a poster that
    goes to a customer with a visible placeholder is worse than one with a gap.
    """
    return MERGE_PATTERN.sub(lambda m: str(values.get(m.group(1), "") or ""), text or "")


def is_hollow(text: str, values: dict) -> bool:
    """Whether a layer has been left saying nothing useful.

    "Call {agent_mobile}" with no number on file renders as a button reading just
    "Call" — worse than no button at all. A layer whose placeholders *all* came back
    empty is therefore dropped: if the only reason it exists is data this workspace
    does not have, it should not reach a customer.

    Text with no placeholders is never hollow, and text where at least one field
    resolved is kept, so ordinary copy is untouched.
    """
    placeholders = MERGE_PATTERN.findall(text or "")
    if not placeholders:
        return False
    return all(not str(values.get(name, "") or "").strip() for name in placeholders)


def has_required(layer: dict, values: dict) -> bool:
    """Whether a layer's declared data dependencies are all present.

    `"requires": "agent_mobile"` or `"requires": ["a", "b"]`. Layers without the key
    are always drawn, so this costs nothing for ordinary designs.
    """
    required = layer.get("requires")
    if not required:
        return True
    names = [required] if isinstance(required, str) else list(required)
    return all(str(values.get(name, "") or "").strip() for name in names)


def _line_width(draw, line: str, font, spacing: float = 0) -> float:
    """Rendered width, including the gaps letter spacing adds between characters."""
    width = draw.textlength(line, font=font)
    if spacing:
        width += spacing * max(0, len(line) - 1)
    return width


def _draw_line(draw, position, line: str, font, fill, spacing: float = 0) -> None:
    """Draw one line, character by character when it is letter-spaced.

    Pillow has no letter-spacing option, so spaced text is drawn a glyph at a time.
    That is slower, which is why the un-spaced path stays a single `draw.text`.
    """
    if not spacing:
        draw.text(position, line, font=font, fill=fill)
        return
    x, y = position
    for character in line:
        draw.text((x, y), character, font=font, fill=fill)
        x += draw.textlength(character, font=font) + spacing


def _wrap(draw, text: str, font, max_width: int, max_lines: int, spacing: float = 0) -> list[str]:
    """Greedy word wrap, truncating with an ellipsis rather than overflowing."""
    if max_width <= 0:
        return [text]
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if _line_width(draw, trial, font, spacing) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and words:
        rendered = " ".join(lines)
        if len(rendered) < len(text):
            last = lines[-1]
            while last and _line_width(draw, last + "…", font, spacing) > max_width:
                last = last[:-1]
            lines[-1] = last + "…"
    return lines


def _rounded(image: Image.Image, radius: int) -> Image.Image:
    """Round the corners without discarding the alpha the image already has.

    `putalpha(mask)` *replaces* the alpha channel, so a half-transparent rectangle
    with rounded corners came out fully opaque — the opacity control silently did
    nothing whenever a radius was set. Multiplying the two keeps both.
    """
    if radius <= 0:
        return image
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.size[0], image.size[1]], radius, fill=255)
    existing = image.getchannel("A")
    # Keep the layer's own alpha inside the rounded area, fully clear outside it.
    image.putalpha(Image.composite(existing, Image.new("L", image.size, 0), mask))
    return image


def _fit(image: Image.Image, width: int, height: int, mode: str = "cover") -> Image.Image:
    """Scale into a box: `cover` crops to fill, `contain` letterboxes."""
    if width <= 0 or height <= 0:
        return image
    source_ratio = image.width / image.height
    target_ratio = width / height

    if mode == "contain":
        scale = min(width / image.width, height / image.height)
        resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
        return canvas

    if source_ratio > target_ratio:
        new_height = height
        new_width = int(height * source_ratio)
    else:
        new_width = width
        new_height = int(width / source_ratio)
    resized = image.resize((max(1, new_width), max(1, new_height)))
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def render(template: dict, values: dict | None = None, assets: dict | None = None) -> bytes:
    """Render one poster to PNG bytes.

    `values` are the merge fields; `assets` maps an image layer's source name to raw
    bytes (logo, agent photo, uploaded background), fetched by the caller so this
    stays free of storage and database concerns.
    """
    values = values or {}
    assets = assets or {}

    width, height = POSTER_SIZES.get(template.get("size", "square"), POSTER_SIZES["square"])
    background = template.get("background") or {}

    base_colour = _colour(background.get("color"), (255, 255, 255, 255))
    gradient = background.get("gradient") or {}
    if gradient.get("to"):
        canvas = _gradient(
            width, height, base_colour, _colour(gradient["to"], base_colour),
            gradient.get("angle", "vertical"),
        )
    else:
        canvas = Image.new("RGBA", (width, height), base_colour)

    if background.get("image") and assets.get(background["image"]):
        try:
            image = Image.open(io.BytesIO(assets[background["image"]])).convert("RGBA")
            canvas.paste(_fit(image, width, height, "cover"), (0, 0))
        except Exception:
            log.exception("Could not draw the poster background")

    # A dark scrim keeps white text legible over a photo of unknown brightness.
    if background.get("overlay"):
        scrim = Image.new("RGBA", (width, height), _colour(background.get("overlay"), (0, 0, 0, 90)))
        canvas = Image.alpha_composite(canvas, scrim)

    draw = ImageDraw.Draw(canvas)

    for layer in template.get("layers") or []:
        kind = layer.get("type")
        x, y = int(layer.get("x", 0)), int(layer.get("y", 0))

        # A layer can depend on data it does not itself display. Dropping the text of
        # "Call {agent_mobile}" would otherwise leave the button's background behind
        # as an empty coloured pill.
        if not has_required(layer, values):
            continue

        try:
            if kind == "rect":
                w, h = int(layer.get("w", 100)), int(layer.get("h", 100))
                fill = _with_opacity(_colour(layer.get("fill"), (0, 0, 0, 255)),
                                     layer.get("opacity"))
                patch = Image.new("RGBA", (max(1, w), max(1, h)), fill)
                patch = _rounded(patch, int(layer.get("radius", 0)))
                canvas.alpha_composite(patch, (x, y))
                draw = ImageDraw.Draw(canvas)

            elif kind == "line":
                # A rect one pixel tall works, but "draw a rule under the heading" is
                # common enough on a poster that making someone reason about a
                # rectangle's height is a small papercut worth removing.
                w, h = int(layer.get("w", 200)), max(1, int(layer.get("h", 4)))
                fill = _with_opacity(_colour(layer.get("fill"), (0, 0, 0, 255)),
                                     layer.get("opacity"))
                patch = Image.new("RGBA", (max(1, w), h), fill)
                patch = _rounded(patch, int(layer.get("radius", 0)))
                canvas.alpha_composite(patch, (x, y))
                draw = ImageDraw.Draw(canvas)

            elif kind == "text":
                raw = str(layer.get("text", ""))
                if is_hollow(raw, values):
                    continue
                text = apply_merge(raw, values)
                if not text.strip():
                    continue
                if layer.get("uppercase"):
                    text = text.upper()
                size = int(layer.get("size", 40))
                font = load_font(
                    size, bool(layer.get("bold")),
                    str(layer.get("font", "sans")), bool(layer.get("italic")),
                )
                box_width = int(layer.get("w", width - x - 40))
                spacing = float(layer.get("letter_spacing", 0) or 0)
                lines = _wrap(draw, text, font, box_width, int(layer.get("max_lines", 4)),
                              spacing)
                line_height = int(size * float(layer.get("line_height", 1.25)))
                align = layer.get("align", "left")
                colour = _colour(layer.get("color"), (17, 24, 39, 255))

                shadow = layer.get("shadow") or {}
                outline = layer.get("outline") or {}
                outline_width = int(outline.get("width", 0) or 0)

                # A partly transparent layer is drawn onto its own transparent sheet
                # and composited, never straight onto the canvas. `draw.text` on an
                # RGBA image *replaces* the pixel rather than blending it, and the
                # final `convert("RGB")` then throws the alpha away — so semi-opaque
                # white text drawn directly came out fully opaque and the opacity
                # control appeared to do nothing at all.
                opacity = _opacity_factor(layer.get("opacity"))
                if opacity < 1.0:
                    sheet = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                    target = ImageDraw.Draw(sheet)
                else:
                    sheet, target = None, draw

                for index, line in enumerate(lines):
                    line_width = _line_width(draw, line, font, spacing)
                    if align == "center":
                        draw_x = x + (box_width - line_width) / 2
                    elif align == "right":
                        draw_x = x + box_width - line_width
                    else:
                        draw_x = x
                    draw_y = y + index * line_height

                    # Shadow first, then outline, then the text — a poster is often
                    # read over a photo, and white-on-white is the commonest way a
                    # design that looked right in the editor arrives unreadable.
                    if shadow.get("color"):
                        _draw_line(target, (draw_x + float(shadow.get("dx", 2)),
                                            draw_y + float(shadow.get("dy", 2))),
                                   line, font, _colour(shadow["color"], (0, 0, 0, 128)), spacing)
                    if outline_width and outline.get("color"):
                        ring = _colour(outline["color"], (0, 0, 0, 255))
                        for ox in range(-outline_width, outline_width + 1):
                            for oy in range(-outline_width, outline_width + 1):
                                if ox or oy:
                                    _draw_line(target, (draw_x + ox, draw_y + oy), line,
                                               font, ring, spacing)
                    _draw_line(target, (draw_x, draw_y), line, font, colour, spacing)

                if sheet is not None:
                    faded = sheet.getchannel("A").point(lambda v: int(v * opacity))
                    sheet.putalpha(faded)
                    canvas.alpha_composite(sheet)
                    draw = ImageDraw.Draw(canvas)

            elif kind == "image":
                source = layer.get("source") or layer.get("asset_key")
                data = assets.get(source)
                if not data:
                    continue
                w, h = int(layer.get("w", 200)), int(layer.get("h", 200))
                image = Image.open(io.BytesIO(data)).convert("RGBA")
                image = _fit(image, w, h, layer.get("fit", "cover"))
                image = _rounded(image, int(layer.get("radius", 0)))
                if layer.get("opacity") is not None:
                    try:
                        alpha = max(0.0, min(1.0, float(layer["opacity"])))
                        faded = image.getchannel("A").point(lambda v: int(v * alpha))
                        image.putalpha(faded)
                    except (TypeError, ValueError):
                        pass
                canvas.alpha_composite(image, (x, y))
                draw = ImageDraw.Draw(canvas)
        except Exception:
            log.exception("Skipped a poster layer that failed to render: %s", kind)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
