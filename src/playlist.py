# Playlist — an Album-like container for playing favourites/playlists.
#
# Quacks enough like Album for Player (tracklist, title, artist) while
# opting out of album-only behavior: `path` is None until App points it at
# the *playing track's* folder on each track change (so lyrics caching and
# per-album accents key correctly per song), `art` is likewise the current
# song's album cover only — never the folder's full art gallery.

from track import Track


class Playlist:
    is_playlist = True

    def __init__(self, title, records, playlist_name=''):
        self.title = title
        # '' = the All Favourites collection; otherwise the stored playlist
        # name (used by the tracklist context menu's "remove from" action)
        self.playlist_name = playlist_name
        self.artist = ''
        self.year = ''
        self.path = None
        self.art = None
        self.art_list = []
        self.tracklist = [
            Track(tracknumber=r.get('tracknumber', 0),
                  title=r.get('title', ''),
                  length=r.get('length', 0),
                  album=r.get('album', ''),
                  artist=r.get('artist', ''),
                  year=r.get('year', ''),
                  filename=r.get('filename', ''),
                  path=r.get('path', ''))
            for r in records]
