# Extract prominent colors from an image for accent color matching

from collections import Counter
from PyQt5.QtGui import QImage, QColor


def extract_palette(image_path, count=5):
    """Identify the most visually prominent colours in an image.

    Focuses on colours that cover large areas or draw the eye,
    filtering out background noise. Returns up to *count* hex codes.
    """
    img = QImage(str(image_path))
    if img.isNull():
        return []

    img = img.scaled(120, 120)
    total_pixels = img.width() * img.height()

    # Bin every pixel by hue/sat/val
    bins = Counter()
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            h, s, v, _ = c.getHsv()
            # Skip near-grey / very dark pixels (background noise)
            if s < 40 or v < 60:
                continue
            h_bin = (h // 12) * 12   # 30 hue buckets
            s_bin = (s // 51) * 51   # 5 sat buckets
            v_bin = (v // 51) * 51   # 5 val buckets
            bins[(h_bin, s_bin, v_bin)] += 1

    if not bins:
        return []

    def to_hex(h, s, v):
        c = QColor.fromHsv(h % 360, min(s + 25, 255), min(v + 25, 255))
        return c.name()

    # Score each bin: area coverage × visual prominence (saturation + value)
    scored = []
    for (h, s, v), freq in bins.items():
        coverage = freq / total_pixels
        prominence = (s / 255) * 0.6 + (v / 255) * 0.4
        score = coverage * prominence
        scored.append(((h, s, v), score))
    scored.sort(key=lambda x: x[1], reverse=True)

    # Pick top colours, skipping near-duplicates
    results = []
    for (h, s, v), _score in scored:
        hex_c = to_hex(h, s, v)
        c = QColor(hex_c)
        too_close = False
        for existing in results:
            ec = QColor(existing)
            # Compare hue distance (wrapping around 360)
            dh = abs(c.hue() - ec.hue())
            dh = min(dh, 360 - dh)
            ds = abs(c.saturation() - ec.saturation())
            dv = abs(c.value() - ec.value())
            if dh < 30 and ds < 60 and dv < 60:
                too_close = True
                break
        if not too_close:
            results.append(hex_c)
        if len(results) >= count:
            break

    return results


def _luminance(c):
    """Relative luminance of a QColor (WCAG formula)."""
    def lin(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())


def _contrast(c1, c2):
    """WCAG contrast ratio between two QColors."""
    l1, l2 = _luminance(c1), _luminance(c2)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def text_color_for(bg_hex):
    """Return 'black' or 'white' for readable text on the given background."""
    bg = QColor(bg_hex)
    # WCAG: use white text on dark backgrounds, black on light
    return 'black' if _luminance(bg) > 0.18 else 'white'


def ensure_contrast(accent_hex, bg_hex, min_ratio=3.0):
    """Adjust accent lightness if it doesn't meet min_ratio contrast against bg.

    Returns the original hex if contrast is sufficient, otherwise a
    lightened or darkened version that meets the threshold.
    """
    accent = QColor(accent_hex)
    bg = QColor(bg_hex)
    if _contrast(accent, bg) >= min_ratio:
        return accent_hex

    # Shift value (brightness) up or down depending on background luminance
    h, s, v, _ = accent.getHsv()
    bg_light = _luminance(bg) > 0.5
    for step in range(1, 40):
        if bg_light:
            new_v = max(0, v - step * 5)
        else:
            new_v = min(255, v + step * 5)
        candidate = QColor.fromHsv(h, s, new_v)
        if _contrast(candidate, bg) >= min_ratio:
            return candidate.name()

    return accent_hex


def most_readable(colors):
    """Pick the colour with the best contrast against both light and dark backgrounds."""
    if not colors:
        return None
    light_bg = QColor('white')
    dark_bg = QColor('#1e1e1e')
    best = None
    best_score = 0
    for hex_c in colors:
        c = QColor(hex_c)
        # Minimum contrast against either background
        score = min(_contrast(c, light_bg), _contrast(c, dark_bg))
        if score > best_score:
            best_score = score
            best = hex_c
    return best
