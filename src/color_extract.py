# Extract prominent colors from an image for accent color matching

from collections import Counter
from PyQt5.QtGui import QImage, QColor


def extract_palette(image_path, count=6):
    """Extract colours that span the hue range found in the image.

    Returns a list of hex color strings spread across the colour spectrum.
    """
    img = QImage(str(image_path))
    if img.isNull():
        return []

    img = img.scaled(100, 100)

    # Bin pixels by hue (ignore greys)
    hue_bins = Counter()
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            h, s, v, _ = c.getHsv()
            if s < 80 or v < 100:
                continue
            h_bin = (h // 15) * 15
            s_bin = (s // 64) * 64
            v_bin = (v // 64) * 64
            hue_bins[(h_bin, s_bin, v_bin)] += 1

    if not hue_bins:
        return []

    # Group by hue, pick the most common sat/val combo per hue
    hue_best = {}
    for (h, s, v), freq in hue_bins.items():
        if h not in hue_best or freq > hue_best[h][1]:
            hue_best[h] = ((h, s, v), freq)

    # Sort by hue to get a rainbow spread
    sorted_hues = sorted(hue_best.keys())

    if len(sorted_hues) <= count:
        picks = [hue_best[h][0] for h in sorted_hues]
    else:
        # Evenly sample across the hue range
        step = len(sorted_hues) / count
        picks = []
        for i in range(count):
            idx = int(i * step)
            h = sorted_hues[idx]
            picks.append(hue_best[h][0])

    def to_hex(h, s, v):
        c = QColor.fromHsv(h % 360, min(s + 15, 255), min(v + 15, 255))
        return c.name()

    # Deduplicate
    seen = set()
    results = []
    for hsv in picks:
        c = to_hex(*hsv)
        if c not in seen:
            seen.add(c)
            results.append(c)

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
