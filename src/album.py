# Album - representation of music album, displayed by AlbumViewer

import os
import re
from pathlib import Path

# local
from track import Track

# mutagen
import mutagen

class Album:
    def __init__(self, directory=""):
        self.tracklist = self.tracklist_from_folder(directory)
        if self.tracklist:
            self.title = self.tracklist[0].album
            self.artist = self.tracklist[0].artist
            self.year = self.tracklist[0].year
            path_split = self.tracklist[0].path.split('/')[:-1]
            self.path = '/'.join(path_split)
            art_path = Path(self.path, 'cover.jpg')
            self.art = art_path if art_path.exists() else None

    def tracklist_from_folder(self, directory_path):
        """
        Generate a tracklist [] of Tracks from a directory that 
        contains .mp3 or .flac audio files.

        param directory_path: a pathlib Path
        """
        def meta_check(tag, default=None):
            """
            helper: return metadata if it exists, return None otherwise
            
            :param tag: list of v
            :param default: None
            """
            try:
                return tag[0]
            except (TypeError, IndexError):
                return default
    
        def int_or_none(value, default=0):
            """
            helper: return tracknumber metadata as integer if exists, otherwise
                        return 0
            
            :param value: Description
            :param default: Description
            """
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def parse_filename(filename):
            """Extract track number and title from filename as fallback."""
            name = os.path.splitext(filename)[0]
            # Match leading digits as track number: "01 Rag Mama Rag" or "01. Rag Mama Rag"
            m = re.match(r'^(\d+)[\s.\-_]+(.+)', name)
            if m:
                return int_or_none(m.group(1)), m.group(2).strip()
            return 0, name

        def infer_artist_album(directory_path):
            """Try to extract artist and album from parent directory names."""
            parts = Path(directory_path).parts
            # Common pattern: .../Artist/Year - Album/CD1/
            # or: .../Artist/Album/
            album_dir = parts[-1] if parts else ''
            # Skip disc subdirectories
            if re.match(r'^(CD|Disc|Disk)\s*\d+$', album_dir, re.IGNORECASE):
                album_dir = parts[-2] if len(parts) > 1 else album_dir
                artist_dir = parts[-3] if len(parts) > 2 else ''
            else:
                artist_dir = parts[-2] if len(parts) > 1 else ''
            # Strip year prefix from album dir: "1978 - The Last Waltz (...)" -> "The Last Waltz"
            album_name = re.sub(r'^\d{4}\s*[-–]\s*', '', album_dir)
            album_name = re.sub(r'\(.*?\)', '', album_name).strip()
            return artist_dir, album_name

        tracklist = []
        root = directory_path
        dir_artist, dir_album = infer_artist_album(directory_path)

        for file in os.listdir(directory_path):
            path = Path(root, file)
            if path.is_dir():
                continue
            if not file.lower().endswith(('.flac', '.mp3', '.m4a')):
                continue
            try:
                track = mutagen.File(path)
            except Exception:
                continue
            if track is None:
                continue
            length = track.info.length if track.info else 0

            if file.lower().endswith('.flac'):
                tracknumber = meta_check(track.get('tracknumber'))
                tracknumber = int_or_none(tracknumber)
                title = meta_check(track.get('title'))
                album_title = meta_check(track.get('album'))
                artist = meta_check(track.get('artist'))
                year = meta_check(track.get('date'))
                tracklist.append(Track(
                    tracknumber=tracknumber,
                    title=title,
                    length=length,
                    album=album_title,
                    artist=artist,
                    year=year,
                    filename=file,
                    path=str(path))
                )

            elif file.lower().endswith('.mp3'):
                tracknumber = meta_check(track.get('TRCK'))
                if tracknumber and '/' in tracknumber:
                    tracknumber = tracknumber.split('/')[0]
                tracknumber = int_or_none(tracknumber)
                title = meta_check(track.get('TIT2'))
                album_title = meta_check(track.get('TALB'))
                artist = meta_check(track.get('TPE1'))
                year = meta_check(track.get('TDRC'))
                tracklist.append(Track(
                    tracknumber=tracknumber,
                    title=title,
                    length=length,
                    album=album_title,
                    artist=artist,
                    year=year,
                    filename=file,
                    path=str(path))
                )

        # Fallback: fill missing metadata from filenames and directory names
        for t in tracklist:
            if not t.title or not t.tracknumber:
                fn_num, fn_title = parse_filename(t.filename)
                if not t.title:
                    t.title = fn_title
                if not t.tracknumber:
                    t.tracknumber = fn_num
            if not t.artist:
                t.artist = dir_artist
            if not t.album:
                t.album = dir_album

        # Filter out full-disc rips (single huge file alongside individual tracks)
        if len(tracklist) > 2:
            lengths = sorted(t.length for t in tracklist)
            median = lengths[len(lengths) // 2]
            if median > 0:
                tracklist = [t for t in tracklist if t.length < median * 5]

        # sort tracklist by track number and return
        tracklist = sorted(tracklist, key=lambda t: t.tracknumber)
        return tracklist
    
    def __str__(self):
        s = ""
        if self.tracklist:
            s = f"{self.artist} - {self.title} ({self.year})\n"
            for track in self.tracklist:
                s += f"{track}\n"
        return s


def main():
    album = Album(Path("/Users/jlm/Downloads/music/Carly Rae Jepsen - Emotion (10th Anniversary Edition) - (2025)"))
    print(album)
    print()
    
if __name__ == "__main__":
    main()
