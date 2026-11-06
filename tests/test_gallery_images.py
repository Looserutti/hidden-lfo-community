from PIL import Image
from pathlib import Path
from app.branding import discover_gallery
from app.gallery_images import variants


def test_responsive_copies_preserve_original_and_refresh_on_replacement(tmp_path):
    folder=tmp_path/'images/gallery';folder.mkdir(parents=True)
    photo=folder/'photo.jpg';Image.new('RGB',(2000,1500),'blue').save(photo)
    original=photo.read_bytes()
    site={'name':'Example','gallery_folder':'images/gallery'}
    item=discover_gallery(site,tmp_path)[0]
    assert item['src']=='/static/images/gallery/photo.jpg'
    assert '480w' in item['srcset'] and '1600w' in item['srcset']
    assert photo.read_bytes()==original
    copy=tmp_path/item['display_src'].removeprefix('/static/')
    assert Image.open(copy).size==(960,720)
    variants.cache_clear()
    assert discover_gallery(site,tmp_path)[0]==item
    Image.new('RGB',(1800,1200),'red').save(photo)
    assert discover_gallery(site,tmp_path)[0]['display_src']!=item['display_src']
    photo.unlink();assert discover_gallery(site,tmp_path)==[]


def test_animated_images_retain_original(tmp_path):
    folder=tmp_path/'images/gallery';folder.mkdir(parents=True)
    Image.new('RGB',(20,20),'red').save(folder/'animation.gif',save_all=True,append_images=[Image.new('RGB',(20,20),'blue')],duration=100,loop=0)
    assert 'display_src' not in discover_gallery({'name':'Example'},tmp_path)[0]


def test_only_first_slide_requests_image_before_javascript():
    from jinja2 import Environment,FileSystemLoader,select_autoescape
    from app.branding import load_site
    from app.calendar_utils import calendar_time
    site=load_site('config/site.example.json')
    site['gallery']=[{'src':'/static/original.jpg','display_src':'/static/small.webp','srcset':'/static/small.webp 960w','alt':'Photo','width':2000,'height':1500}]*2
    env=Environment(loader=FileSystemLoader('templates'),autoescape=select_autoescape())
    env.filters['calendar_time']=calendar_time
    html=env.get_template('index.html').render(site=site,events=[])
    assert html.count('fetchpriority="high"')==1
    assert html.count('data-src="/static/small.webp"')==1
    assert html.count('data-full-src="/static/original.jpg"')==2
