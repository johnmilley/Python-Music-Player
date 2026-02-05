# Track contains all of the metadata for a music file

import math

class Track:
    def __init__(self, tracknumber=0, title='', length=0, album='', artist='', year=0, filename='', path=''):
        self.tracknumber = tracknumber
        self.title = title
        self.length = length
        self.album = album
        self.artist = artist
        self.year = year
        self.filename = filename # fallback display
        self.path = path         # for playback

    def length_to_string(self, length:int):
        minutes = math.floor(length / 60) 
        seconds = str(math.floor(length - (minutes * 60)))
        if len(seconds) == 1:
            seconds = "0" + seconds
        return f"{minutes}:{seconds}"
        
    def __repr__(self):
        if self.tracknumber and self.title:
            return f"{self.tracknumber}. {self.title} ({self.length_to_string(self.length)})"
        else:
            return f"{self.filename} ({self.length_to_string(self.length)})" # fallback

def main():
    t = Track()
    t.length = 185
    print(t)
    print(t.length_to_string(t.length))

if __name__ == "__main__":
    main()