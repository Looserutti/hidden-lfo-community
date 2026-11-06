"""Responsive display copies; originals remain unchanged for the photo viewer."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from uuid import uuid4
import warnings


@lru_cache(maxsize=128)
def variants(filename, modified, byte_size, static_root):
    from PIL import Image, ImageOps, UnidentifiedImageError
    source=Path(filename);root=Path(static_root)
    try:
        identity=hashlib.sha256(b'carousel-webp-v1'+source.read_bytes()).hexdigest()[:24]
        folder=root/'gallery-optimized';folder.mkdir(exist_ok=True)
        manifest=folder/f'{identity}.json'
        if manifest.is_file():
            saved=json.loads(manifest.read_text())
            if all((root / url.removeprefix('/static/')).is_file() for url in saved.pop('files')):
                return saved
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(source) as original:
                if getattr(original,'is_animated',False) or original.width*original.height>40_000_000:return {}
                image=ImageOps.exif_transpose(original).convert('RGB' if original.mode not in ('RGBA','LA') else 'RGBA')
        widths=sorted({min(width,image.width) for width in (480,960,1600)})
        copies=[]
        for width in widths:
            target=folder/f'{identity}-{width}.webp'
            if not target.is_file():
                resized=image.resize((width,max(1,round(image.height*width/image.width))),Image.Resampling.LANCZOS)
                temporary=folder/(uuid4().hex+'.tmp')
                try:
                    resized.save(temporary,format='WEBP',quality=80,method=4)
                    temporary.replace(target)
                finally:temporary.unlink(missing_ok=True)
            copies.append((width,'/static/gallery-optimized/'+target.name))
        preferred=min(copies,key=lambda row:abs(row[0]-960))[1]
        result=dict(display_src=preferred,srcset=', '.join(f'{url} {width}w' for width,url in copies),width=image.width,height=image.height)
        temporary=folder/(uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps({**result,'files':[url for _,url in copies]}))
            temporary.replace(manifest)
        finally:temporary.unlink(missing_ok=True)
        return result
    except (OSError,ValueError,KeyError,Image.DecompressionBombError,Image.DecompressionBombWarning,UnidentifiedImageError):
        # Existing formats, animation and unreadable files retain the original behavior.
        return {}
