"""Standalone image decoder; copied into a credential-free sandbox job directory."""
import json
from pathlib import Path
import warnings
from PIL import Image, ImageOps

warnings.simplefilter('error',Image.DecompressionBombWarning)
root=Path.cwd()
request=json.loads((root/'request.json').read_text())
results=[]
for index,name in enumerate(request):
    with Image.open(root/name) as opened:
        if opened.format not in {'JPEG','PNG','WEBP','AVIF'} or getattr(opened,'is_animated',False):
            raise ValueError('Use still JPEG, PNG, WebP or AVIF images.')
        if opened.width*opened.height>40_000_000:raise ValueError('Image exceeds 40 megapixels.')
        image=ImageOps.exif_transpose(opened)
        image.thumbnail((3200,3200),Image.Resampling.LANCZOS)
        # Flatten transparency onto a neutral background; strip EXIF/GPS metadata.
        if 'A' in image.getbands():
            rgba=image.convert('RGBA');image=Image.new('RGB',rgba.size,'#151515');image.paste(rgba,mask=rgba.getchannel('A'))
        else:image=image.convert('RGB')
        image.save(root/f'{index:02d}-full.jpg',quality=92,optimize=True)
        for size in (480,960,1600):
            copy=image.copy();copy.thumbnail((size,size),Image.Resampling.LANCZOS)
            copy.save(root/f'{index:02d}-{size}.webp',format='WEBP',quality=80,method=4)
        results.append({'width':image.width,'height':image.height})
(root/'result.json').write_text(json.dumps(results))
