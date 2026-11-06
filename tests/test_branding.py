from app.branding import discover_gallery


def test_gallery_updates_after_file_changes(tmp_path):
    folder = tmp_path / 'images/gallery'
    folder.mkdir(parents=True)
    site = {'name': 'Test Community', 'gallery_folder': 'images/gallery'}
    assert discover_gallery(site, tmp_path) == []
    for name in ('photo-10.JPG', 'photo-2.jpg', 'crowd #1.png', '.hidden.jpg', 'original.HEIC', 'notes.txt'):
        (folder / name).touch()
    (folder / 'nested.jpg').mkdir()
    (folder / 'link.jpg').symlink_to(folder / 'photo-2.jpg')
    photos = discover_gallery(site, tmp_path)
    assert [p['src'] for p in photos] == [
        '/static/images/gallery/crowd%20%231.png',
        '/static/images/gallery/photo-2.jpg',
        '/static/images/gallery/photo-10.JPG',
    ]
    assert photos[0]['alt'] == 'Test Community — crowd #1'
    (folder / 'photo-2.jpg').unlink()
    assert len(discover_gallery(site, tmp_path)) == 2


def test_missing_gallery_folder_is_empty(tmp_path):
    assert discover_gallery({'name': 'Test Community'}, tmp_path) == []


def test_generic_branding_renders_without_accounts_or_photos(tmp_path):
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from app.branding import load_site
    site = load_site('config/site.example.json')
    site['gallery'] = discover_gallery(site, tmp_path)
    site['name'] = '<Another Community>'
    env = Environment(loader=FileSystemLoader('templates'), autoescape=select_autoescape())
    from app.calendar_utils import calendar_time
    env.filters['calendar_time'] = calendar_time
    html = env.get_template('index.html').render(site=site, events=[])
    assert '&lt;Another Community&gt;' in html
    assert 'class="home-gallery"' not in html
    assert 'instagram.com' not in html
    assert 'Hidden LFO' not in html
    assert 'href="/login"' in html


def test_config_rejects_unsafe_urls_and_gallery_paths(tmp_path):
    import json
    import pytest
    from app.branding import load_site
    source = load_site('config/site.example.json')
    config = tmp_path / 'site.json'
    for changes in ({'gallery_folder': '../private'}, {'socials': {'instagram': 'javascript:alert(1)'}}):
        config.write_text(json.dumps({**source, **changes}))
        with pytest.raises(ValueError):
            load_site(config)
