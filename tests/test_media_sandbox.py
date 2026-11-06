import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave
import math
import struct
import pytest
from app import media_process


def test_unsupported_input_never_starts_ffmpeg(tmp_path):
    with pytest.raises(ValueError,match='MP3'):
        media_process.run_audio(tmp_path/'playlist.m3u8',[])


def test_clean_environment_and_fail_closed(tmp_path,monkeypatch):
    source=tmp_path/'source.wav';source.write_bytes(b'test')
    monkeypatch.setattr(media_process,'available',lambda:True)
    monkeypatch.setattr(media_process.shutil,'which',lambda _: '/usr/bin/ffmpeg')
    monkeypatch.setenv('DISCORD_BOT_TOKEN','fake-sensitive-value')
    def fake_run(args,**kwargs):
        assert 'DISCORD_BOT_TOKEN' not in kwargs['env']
        assert 'SESSION_SECRET' not in kwargs['env']
        assert kwargs['close_fds']
        assert args[1]=='-I'
        assert '-protocol_whitelist' in args and '-codec_whitelist' in args
        return type('Result',(),{'returncode':125})()
    monkeypatch.setattr(media_process.subprocess,'run',fake_run)
    with pytest.raises(ValueError,match='isolation'):
        media_process.run_audio(source,[])


@pytest.mark.skipif(sys.platform!='linux',reason='Linux kernel isolation tested in release container')
def test_kernel_blocks_other_files_and_network(tmp_path):
    from app import media_sandbox
    job=tmp_path/'job';job.mkdir()
    outside=tmp_path/'private.env';outside.write_text('fake-secret')
    code='''import os,socket,json,threading
from pathlib import Path
result={}
for name,path,mode in [('read',os.environ['OUTSIDE'],'r'),('write',os.environ['OUTSIDE'],'w')]:
 try:
  with open(path,mode) as f:pass
  result[name]=False
 except PermissionError:result[name]=True
try:socket.socket();result['network']=False
except PermissionError:result['network']=True
try:os.fork();result['fork']=False
except PermissionError:result['fork']=True
thread=threading.Thread(target=lambda:None);thread.start();thread.join()
Path('allowed.txt').write_text('ok')
print(json.dumps(result))
'''
    result=subprocess.run([sys.executable,'-I',str(Path(media_sandbox.__file__).resolve()),str(job),sys.executable,'-I','-c',code],
                          env={'PATH':'/usr/bin:/bin','LANG':'C','OUTSIDE':str(outside)},capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)=={'read':True,'write':True,'network':True,'fork':True}
    assert outside.read_text()=='fake-secret'
    assert (job/'allowed.txt').read_text()=='ok'


@pytest.mark.skipif(not media_process.available(),reason='Requires Linux release FFmpeg')
def test_supported_formats_still_measure_and_disguised_playlist_is_rejected(tmp_path):
    from app.normalization import measure
    source=tmp_path/'tone.wav'
    with wave.open(str(source),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(44100)
        stream.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(2*math.pi*440*i/44100))) for i in range(44100)))
    assert all(math.isfinite(x) for x in measure(source))
    for suffix,codec in [('.mp3','libmp3lame'),('.m4a','aac'),('.m4a','alac')]:
        target=tmp_path/(codec+suffix)
        subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-i',str(source),'-c:a',codec,str(target)],check=True)
        assert all(math.isfinite(x) for x in measure(target))
    spoof=tmp_path/'spoof.wav';spoof.write_text('#EXTM3U\nhttps://example.org/stream\n')
    with pytest.raises(ValueError,match='decoded'):measure(spoof)
