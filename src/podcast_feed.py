# Podcast RSS feed parser and data classes
# PodcastFeed mimics Album, PodcastEpisode mimics Track for Player compatibility

import os
import re
import hashlib
import xml.etree.ElementTree as ET
from html import unescape
from pathlib import Path
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from PyQt5.QtCore import QThread, pyqtSignal

# Cache directory for downloaded episodes — platform-appropriate location
import sys
if sys.platform == 'darwin':
    CACHE_DIR = Path.home() / 'Library' / 'Caches' / 'lp' / 'podcasts'
elif sys.platform == 'win32':
    CACHE_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'lp' / 'cache' / 'podcasts'
else:
    CACHE_DIR = Path.home() / '.cache' / 'lp' / 'podcasts'

# Session with User-Agent — some feed servers block bare requests
_session = requests.Session()
_session.headers['User-Agent'] = 'lp-podcast/1.0'


class PodcastEpisode:
    """Track-compatible data class for a podcast episode."""

    def __init__(self, title='', length=0, artist='', album='',
                 audio_url='', description='', pub_date=None, guid='',
                 episode_type='full'):
        self.title = str(title) if title else ''
        self.length = length          # duration in seconds
        self.artist = str(artist)     # podcast name
        self.album = str(album)       # podcast name
        self.year = ''
        self.tracknumber = 0
        self.filename = ''
        self.path = ''                # set after download

        # Podcast-specific
        self.audio_url = audio_url
        self.description = str(description) if description else ''
        self.pub_date = pub_date
        self.guid = guid
        self.episode_type = episode_type

    @property
    def date_str(self):
        if self.pub_date:
            return self.pub_date.strftime('%b %d, %Y')
        return ''

    def cache_path(self):
        """Return the local cache path for this episode's audio."""
        slug = hashlib.md5(self.guid.encode()).hexdigest()[:12]
        return CACHE_DIR / f'{slug}.mp3'

    @property
    def is_downloaded(self):
        p = self.cache_path()
        return p.exists() and p.stat().st_size > 0

    def length_to_string(self, length):
        total_seconds = int(length)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    def __repr__(self):
        dur = self.length_to_string(self.length)
        return f"{self.title} ({dur})"


class PodcastFeed:
    """Album-compatible container for a podcast feed."""

    def __init__(self, url='', title='', description='', image_url='',
                 episodes=None):
        self.url = url
        self.title = str(title) if title else ''
        self.artist = self.title      # for Player compatibility
        self.description = str(description) if description else ''
        self.image_url = image_url
        self.year = ''
        self.path = str(CACHE_DIR)
        self.art = None               # set after image download
        self.tracklist = episodes or []

    @staticmethod
    def from_url(url):
        """Fetch and parse a podcast from a URL.

        Accepts Apple Podcasts links (resolved via iTunes Lookup API)
        or direct RSS feed URLs.
        """
        if 'podcasts.apple.com' in url or 'itunes.apple.com' in url:
            feed_url = resolve_apple_url(url)
        else:
            feed_url = url
        resp = _session.get(feed_url, timeout=15)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
        return PodcastFeed.from_xml(resp.text, feed_url)

    @staticmethod
    def from_xml(xml_text, url=''):
        """Parse RSS XML into a PodcastFeed."""
        root = ET.fromstring(xml_text)
        channel = root.find('channel')
        if channel is None:
            return PodcastFeed(url=url)

        ns = {
            'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
            'media': 'http://search.yahoo.com/mrss/',
        }

        title = _text(channel, 'title') or ''
        description = _strip_html(_text(channel, 'itunes:summary', ns)
                                  or _text(channel, 'description') or '')

        # Image
        image_url = ''
        itunes_img = channel.find('itunes:image', ns)
        if itunes_img is not None:
            image_url = itunes_img.get('href', '')
        if not image_url:
            img_el = channel.find('image')
            if img_el is not None:
                image_url = _text(img_el, 'url') or ''

        # Episodes
        episodes = []
        for item in channel.findall('item'):
            ep_title = _text(item, 'title') or _text(item, 'itunes:title', ns) or ''

            # Duration
            dur_str = _text(item, 'itunes:duration', ns) or ''
            duration = _parse_duration(dur_str)

            # Audio URL from enclosure
            audio_url = ''
            enclosure = item.find('enclosure')
            if enclosure is not None:
                audio_url = enclosure.get('url', '')

            # Description
            ep_desc = _strip_html(_text(item, 'itunes:summary', ns)
                                  or _text(item, 'description') or '')

            # Date
            pub_date = None
            date_str = _text(item, 'pubDate')
            if date_str:
                try:
                    pub_date = parsedate_to_datetime(date_str)
                except Exception:
                    pass

            guid = _text(item, 'guid') or audio_url or ep_title

            ep = PodcastEpisode(
                title=ep_title,
                length=duration,
                artist=title,
                album=title,
                audio_url=audio_url,
                description=ep_desc,
                pub_date=pub_date,
                guid=guid,
            )
            if audio_url:
                episodes.append(ep)

        feed = PodcastFeed(
            url=url,
            title=title,
            description=description,
            image_url=image_url,
            episodes=episodes,
        )
        feed.tracklist = episodes
        return feed


class FeedFetchThread(QThread):
    """Background thread to fetch and parse a podcast feed."""
    finished = pyqtSignal(object)  # PodcastFeed or None
    error = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            feed = PodcastFeed.from_url(self.url)
            self.finished.emit(feed)
        except Exception as e:
            print(f"LOG: Feed fetch error: {e}")
            self.error.emit(str(e))


class EpisodeDownloadThread(QThread):
    """Background thread to download a podcast episode."""
    progress = pyqtSignal(int)   # percentage
    finished = pyqtSignal(str)   # local file path
    error = pyqtSignal(str)

    def __init__(self, episode, parent=None):
        super().__init__(parent)
        self.episode = episode

    def run(self):
        try:
            ep = self.episode
            dest = ep.cache_path()
            dest.parent.mkdir(parents=True, exist_ok=True)

            if ep.is_downloaded:
                self.finished.emit(str(dest))
                return

            resp = _session.get(ep.audio_url, stream=True, timeout=30)
            resp.raise_for_status()
            total = int(resp.headers.get('content-length', 0))
            downloaded = 0

            with open(dest, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.progress.emit(int(downloaded / total * 100))

            self.finished.emit(str(dest))
        except Exception as e:
            self.error.emit(str(e))


class ImageDownloadThread(QThread):
    """Background thread to download podcast artwork."""
    finished = pyqtSignal(str)  # local file path

    def __init__(self, url, feed_title, parent=None):
        super().__init__(parent)
        self.url = url
        self.feed_title = feed_title

    def run(self):
        try:
            slug = hashlib.md5(self.feed_title.encode()).hexdigest()[:12]
            dest = CACHE_DIR / f'{slug}_cover.jpg'
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists():
                self.finished.emit(str(dest))
                return

            resp = _session.get(self.url, timeout=15)
            resp.raise_for_status()
            with open(dest, 'wb') as f:
                f.write(resp.content)
            self.finished.emit(str(dest))
        except Exception:
            pass


# Helpers

def resolve_apple_url(url):
    """Resolve an Apple Podcasts link to an RSS feed URL.

    Extracts the numeric podcast ID from URLs like:
      https://podcasts.apple.com/us/podcast/ideas/id151485663?uo=4
    Then queries the iTunes Lookup API for the feed URL.
    """
    match = re.search(r'/id(\d+)', url)
    if not match:
        raise ValueError('Not a valid Apple Podcasts link (no podcast ID found)')
    podcast_id = match.group(1)
    resp = _session.get(
        f'https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast',
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data.get('results', [])
    if not results:
        raise ValueError(f'No podcast found for ID {podcast_id}')
    feed_url = results[0].get('feedUrl')
    if not feed_url:
        raise ValueError(f'No RSS feed URL found for podcast ID {podcast_id}')
    return feed_url


def _strip_html(text):
    """Strip HTML tags and decode entities to plain text."""
    if not text:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _text(element, tag, ns=None):
    """Get text content of a sub-element."""
    child = element.find(tag, ns) if ns else element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


def _parse_duration(s):
    """Parse duration string like '54:09' or '01:04:42' or '3249' to seconds."""
    if not s:
        return 0
    parts = s.split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        else:
            return int(parts[0])
    except ValueError:
        return 0
