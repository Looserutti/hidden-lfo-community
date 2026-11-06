"""Public presentation settings; independent of Discord and event services."""
import json
from pathlib import Path
from urllib.parse import urlsplit, quote
import re
from zoneinfo import ZoneInfo


def load_site(path=None):
    path = Path(path) if path else Path(__file__).resolve().parent.parent / 'config/site.json'
    site = json.loads(path.read_text())
    for key in ('name', 'eyebrow', 'description', 'footer_text'):
        if not isinstance(site.get(key), str):
            raise ValueError(f'Site setting {key} must be text')
    for platform, url in site.get('socials', {}).items():
        if platform not in ('instagram', 'tiktok', 'youtube'):
            raise ValueError(f'Unsupported social platform: {platform}')
        if url and (urlsplit(url).scheme != 'https' or not urlsplit(url).netloc):
            raise ValueError(f'{platform} requires a full HTTPS URL or an empty string')
    folder = Path(site.get('gallery_folder', 'images/gallery'))
    if folder.is_absolute() or '..' in folder.parts or not folder.parts:
        raise ValueError('gallery_folder must be a relative folder inside static/')
    ZoneInfo(site.get("calendar_timezone", "UTC"))
    schedule = site.get('calendar_collection', {'weekday': 1, 'hour': 9})
    if (not isinstance(schedule, dict) or type(schedule.get('weekday')) is not int
            or type(schedule.get('hour')) is not int or not 0 <= schedule['weekday'] <= 6
            or not 0 <= schedule['hour'] <= 23):
        raise ValueError('calendar_collection requires weekday 0–6 and hour 0–23')
    return site


def discover_gallery(site, static_root=None):
    """Rescan on each page request, so file additions/removals need no restart."""
    static_root = Path(static_root) if static_root else Path(__file__).resolve().parent.parent / 'static'
    folder = static_root / site.get('gallery_folder', 'images/gallery')
    if not folder.is_dir():
        return []
    def natural_key(path):
        return [int(part) if part.isdigit() else part.casefold()
                for part in re.split(r'(\d+)', path.name)]
    photos = []
    for path in sorted(folder.iterdir(), key=lambda p: (natural_key(p), p.name)):
        if (path.name.startswith('.') or path.is_symlink() or not path.is_file()
                or path.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}):
            continue
        label = re.sub(r'[_-]+', ' ', path.stem).strip()
        photos.append({'src': '/static/' + quote(path.relative_to(static_root).as_posix(), safe='/'),
                       'alt': f"{site['name']} — {label}"})
    return photos


def site_context():
    return {**SITE, 'gallery': discover_gallery(SITE)}


SITE = load_site()
