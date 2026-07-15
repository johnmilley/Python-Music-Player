# Extract prominent colors from an image for accent color matching

from collections import Counter
from PyQt5.QtGui import QImage, QColor
from PyQt5.QtCore import QThread, pyqtSignal


def extract_palette(image_path, count=5):
    """Identify the most visually prominent colours in an image.

    Focuses on colours that cover large areas or draw the eye,
    filtering out background noise. Returns up to *count* hex codes.
    """
    img = QImage(str(image_path))
    if img.isNull():
        return []

    # Downsample to 60x60 instead of 120x120 — 4x fewer pixels, same results
    img = img.scaled(60, 60)
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

    h, s, l, _ = accent.getHsl()
    bg_light = _luminance(bg) > 0.5

    # Warm/yellow-ish hues (orange, gold) carry a disproportionate share of
    # WCAG luminance in their green channel for how dark they actually look
    # — matching a numeric contrast ratio by crushing lightness alone (the
    # old approach: hold HSV saturation at max, walk value down) pushes
    # them straight into "brown", since a saturated, near-black
    # yellow-orange IS what brown looks like. Cooler hues (blue, rose,
    # lavender) just read as a deeper version of themselves at low
    # lightness, which is why this only ever showed up as an orange/gold
    # bug. A small, FIXED (not scaling with how much correction is needed)
    # nudge toward red trades a little hue for a lot of luminance headroom
    # — red carries much less green — so the lightness ramp that follows
    # needs to go much less far, keeping the result closer to its original
    # brightness. Fixed rather than proportional so presets that started
    # further apart in hue (e.g. Gold vs Orange) stay just as distinct
    # afterward instead of converging on the same corrected color.
    if bg_light and 15 <= h <= 70:
        h = max(12, h - 15)
        accent = QColor.fromHsl(round(h), s, l)
        if _contrast(accent, bg) >= min_ratio:
            return accent.name()

    # Lightness ramp (not HSV value) for whatever contrast gap remains,
    # tapering saturation down alongside it so the result reads as a
    # deeper/lighter shade of the same hue rather than washing out.
    for step in range(1, 40):
        if bg_light:
            new_l = max(0, l - step * 5)
        else:
            new_l = min(255, l + step * 5)
        new_s = round(s * (new_l / l) ** 0.5) if l > 0 else s
        new_s = max(0, min(255, new_s))
        candidate = QColor.fromHsl(round(h), new_s, new_l)
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


class PaletteExtractThread(QThread):
    """Extract color palette in a background thread."""
    # Named palette_ready (not 'finished') so QThread's own finished signal
    # stays usable for lifecycle handling — see bg_threads.retire()
    palette_ready = pyqtSignal(list)  # list of hex color strings

    def __init__(self, image_path, count=5):
        super().__init__()
        self.image_path = image_path
        self.count = count

    def run(self):
        colors = extract_palette(self.image_path, self.count)
        self.palette_ready.emit(colors)
