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
                  "line_height": 1.2, "max_lines": 3}
{"type": "image", "x": 60, "y": 700, "w": 240, "h": 240, "source": "logo|agent_photo|asset",
                  "asset_key": "...", "radius": 0, "fit": "cover"}
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
_FONT_CANDIDATES = {
    False: [  # regular
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ],
    True: [  # bold
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ],
}

_font_cache: dict[tuple[bool, int], Any] = {}
_warned = False


def load_font(size: int, bold: bool = False):
    global _warned
    key = (bold, size)
    if key in _font_cache:
        return _font_cache[key]

    for path in _FONT_CANDIDATES[bold]:
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


def _wrap(draw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    """Greedy word wrap, truncating with an ellipsis rather than overflowing."""
    if max_width <= 0:
        return [text]
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width or not current:
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
            while last and draw.textlength(last + "…", font=font) > max_width:
                last = last[:-1]
            lines[-1] = last + "…"
    return lines


def _rounded(image: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return image
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, image.size[0], image.size[1]], radius, fill=255)
    image.putalpha(mask)
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

    canvas = Image.new("RGBA", (width, height), _colour(background.get("color"), (255, 255, 255, 255)))

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
                fill = _colour(layer.get("fill"), (0, 0, 0, 255))
                if layer.get("opacity") is not None:
                    fill = fill[:3] + (int(255 * float(layer["opacity"])),)
                patch = Image.new("RGBA", (max(1, w), max(1, h)), fill)
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
                size = int(layer.get("size", 40))
                font = load_font(size, bool(layer.get("bold")))
                box_width = int(layer.get("w", width - x - 40))
                lines = _wrap(draw, text, font, box_width, int(layer.get("max_lines", 4)))
                line_height = int(size * float(layer.get("line_height", 1.25)))
                align = layer.get("align", "left")
                colour = _colour(layer.get("color"), (17, 24, 39, 255))

                for index, line in enumerate(lines):
                    line_width = draw.textlength(line, font=font)
                    if align == "center":
                        draw_x = x + (box_width - line_width) / 2
                    elif align == "right":
                        draw_x = x + box_width - line_width
                    else:
                        draw_x = x
                    draw.text((draw_x, y + index * line_height), line, font=font, fill=colour)

            elif kind == "image":
                source = layer.get("source") or layer.get("asset_key")
                data = assets.get(source)
                if not data:
                    continue
                w, h = int(layer.get("w", 200)), int(layer.get("h", 200))
                image = Image.open(io.BytesIO(data)).convert("RGBA")
                image = _fit(image, w, h, layer.get("fit", "cover"))
                image = _rounded(image, int(layer.get("radius", 0)))
                canvas.alpha_composite(image, (x, y))
                draw = ImageDraw.Draw(canvas)
        except Exception:
            log.exception("Skipped a poster layer that failed to render: %s", kind)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()
