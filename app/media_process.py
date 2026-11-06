"""Bounded FFmpeg invocation over one staged input and optional MP3 output."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

FORMATS={'.mp3':'mp3','.wav':'wav','.m4a':'mov'}
CODECS='mp3,mp3float,aac,aac_fixed,alac,pcm_u8,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,pcm_s16be,pcm_s24be,pcm_s32be,pcm_f32be,pcm_f64be,pcm_alaw,pcm_mulaw,adpcm_ima_wav,adpcm_ms'


def available():
    return sys.platform=='linux' and shutil.which('ffmpeg') is not None


def run_audio(source, options, output=None):
    source=Path(source)
    if source.suffix.lower() not in FORMATS:raise ValueError('Use an MP3, WAV or M4A audio file.')
    if not available():raise ValueError('Secure volume processing requires the Linux deployment.')
    binary=shutil.which('ffmpeg')
    with tempfile.TemporaryDirectory(prefix='community-audio-') as directory:
        job=Path(directory)
        staged=job/('input'+source.suffix.lower())
        shutil.copyfile(source,staged);staged.chmod(0o600)
        destination=job/'output.mp3'
        args=[binary,'-nostdin','-hide_banner','-nostats','-threads','2','-filter_threads','1',
              '-protocol_whitelist','file,pipe','-format_whitelist',FORMATS[source.suffix.lower()],
              '-codec_whitelist',CODECS,'-f',FORMATS[source.suffix.lower()],'-i',str(staged),
              '-map','0:a:0','-vn','-sn','-dn',*options,str(destination) if output else '-']
        env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','HOME':directory,'TMPDIR':directory,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1'}
        wrapper=Path(__file__).with_name('media_sandbox.py').resolve()
        with tempfile.TemporaryFile() as log:
            result=subprocess.run([sys.executable,'-I',str(wrapper),directory,*args],env=env,cwd=directory,
                close_fds=True,stdout=subprocess.DEVNULL,stderr=log,timeout=300)
            log.seek(0,2);length=log.tell();log.seek(max(0,length-65536));stderr=log.read().decode('utf-8',errors='replace')
        if result.returncode==125:raise ValueError('Audio isolation is unavailable; volume processing was stopped safely.')
        if result.returncode==0 and output:
            if not destination.is_file() or not destination.stat().st_size:raise ValueError('No playback copy was created.')
            shutil.copyfile(destination,output);Path(output).chmod(0o600)
        return SimpleNamespace(returncode=result.returncode,stderr=stderr)
