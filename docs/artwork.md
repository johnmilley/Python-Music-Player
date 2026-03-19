# Artwork

lp displays album art from a `cover.jpg` in the album folder. It also provides a built-in artwork finder for downloading covers.

## How album art is loaded

When an album folder is loaded, `album.py` looks for a `cover.jpg` in the album directory. If found, it is displayed in the player's center panel and, in max mode, as a large scaled image.

## Artwork finder

Accessible from the menu, the artwork finder searches the **iTunes Search API** for album covers:

1. Opens a dialog pre-filled with the current album's artist and title
2. Sends a search query to `https://itunes.apple.com/search`
3. Displays thumbnail results with artist, album name, and a download button
4. Thumbnails are loaded in background threads (`ImageLoader`)
5. Downloading fetches the high-resolution version (replacing `100x100` with `3000x3000` in the URL)
6. Saves as `cover.jpg` in the album folder (backs up any existing cover first)

After downloading, the player reloads the art and re-extracts the color palette for the accent color.

## Color extraction

`color_extract.py` derives an accent color from album art:

1. Scale image to 120x120 pixels
2. Bin every pixel by hue, saturation, and value (30 hue buckets x 5 sat x 5 val)
3. Filter out near-grey (`saturation < 40`) and very dark (`value < 60`) pixels
4. Score each bin: `coverage * prominence` where prominence weights saturation (60%) and value (40%)
5. Pick top colors, skipping near-duplicates (within 30 hue, 60 sat, 60 val)
6. Select the most readable color using **WCAG contrast ratios** against both light and dark backgrounds

This ensures the accent color and text are always legible regardless of which theme is active.
