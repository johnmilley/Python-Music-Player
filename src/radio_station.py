# Radio station data class


class RadioStation:
    """Minimal Track-compatible data class for a radio stream."""

    def __init__(self, name='', stream_url=''):
        self.title = str(name) if name else ''
        self.name = self.title
        self.stream_url = stream_url
        self.artist = ''
        self.album = ''
        self.length = 0
        self.path = ''
        self.filename = ''

    def __repr__(self):
        return self.name or self.stream_url
