"""Build-time only: fetch pinned dependencies. Never invoked by the converter."""
from pathlib import Path
import json, hashlib, urllib.request
BASE=Path(__file__).resolve().parent.parent.parent
DEST=BASE/'work/downloads'; DEST.mkdir(parents=True,exist_ok=True)
LOCK=Path(__file__).with_name('download-lock.json')

def main():
    entries=json.loads(LOCK.read_text('utf-8'))
    for name,item in entries.items():
        target=DEST/name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']:
            print('Verified:',name); continue
        print('Download:',name,flush=True)
        request=urllib.request.Request(item['url'],headers={'User-Agent':'DICOMPortableBuild/1.0'})
        data=urllib.request.urlopen(request,timeout=180).read()
        if hashlib.sha256(data).hexdigest()!=item['sha256']:
            raise RuntimeError('SHA256 mismatch: '+name+'; upstream content changed, do not use it without review')
        target.write_bytes(data)
if __name__=='__main__': main()
