from html.parser import HTMLParser
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.branding import load_site
import json
import pytest


class Tags(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            self.meta[attrs.get('property', attrs.get('name'))] = attrs.get('content')


def render(site):
    env = Environment(loader=FileSystemLoader('templates'), autoescape=select_autoescape())
    from app.calendar_utils import calendar_time
    env.filters['calendar_time'] = calendar_time
    return env.get_template('index.html').render(site={**site, 'gallery': []}, events=[], share_url='https://community.test/')


def test_homepage_card_matches_approved_content():
    tags = Tags(render(load_site()))
    assert tags.meta['og:title'] == 'Hidden LFO'
    assert tags.meta['og:description'] == 'electronic music and art collective'
    assert tags.meta['og:url'] == 'https://community.test/'
    assert tags.meta['og:image'] == 'https://community.test/static/images/share/homepage-v1.jpg'
    assert tags.meta['twitter:image'] == tags.meta['og:image']
    assert tags.meta['twitter:card'] == 'summary_large_image'


def test_generic_community_has_own_escaped_metadata_without_image():
    site = load_site('config/site.example.json')
    site.update(name='A "new" <community>', description='Art & music')
    html = render(site)
    tags = Tags(html)
    assert tags.meta['og:title'] == site['name']
    assert tags.meta['og:description'] == site['description']
    assert 'og:image' not in tags.meta
    assert 'Hidden LFO' not in html
    assert '&lt;community&gt;' in html


@pytest.mark.parametrize('path', ['https://other.test/photo.jpg', '/static/../private', '/static/photo.jpg?x=1', '//other.test/photo.jpg'])
def test_sharing_image_rejects_unsafe_paths(tmp_path, path):
    site = load_site('config/site.example.json')
    site['share_image'] = path
    config = tmp_path / 'site.json'
    config.write_text(json.dumps(site))
    with pytest.raises(ValueError):
        load_site(config)
