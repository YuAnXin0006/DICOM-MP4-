from pathlib import Path
import zipfile, shutil, hashlib, json
HERE=Path(__file__).resolve().parent
BASE=HERE.parent.parent
DL=BASE/'work'/'downloads'
DEST=BASE/'work'/'package'/'DICOM转MP4工具包'

def build():
    for d in ['原始文件','视频输出','转换记录','程序/python/Lib/site-packages','程序/ffmpeg','第三方许可','构建与验证']:
        (DEST/d).mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(DL/'python-3.12.10-embed-amd64.zip') as z: z.extractall(DEST/'程序/python')
    (DEST/'程序/python/python312._pth').write_text('python312.zip\n.\nLib/site-packages\n..\nimport site\n',encoding='ascii')
    for wheel in DL.glob('*.whl'):
        if wheel.name.startswith('imageio'): continue
        with zipfile.ZipFile(wheel) as z:
            for entry in z.namelist():
                if entry.startswith(('pydicom/data/test_files/','pydicom/data/charset_files/')): continue
                z.extract(entry,DEST/'程序/python/Lib/site-packages')
            for name in z.namelist():
                if any(x in name.upper() for x in ['LICENSE','COPYING','NOTICE']) and not name.endswith('/'):
                    out=DEST/'第三方许可'/wheel.name/(name.replace('/','__'))
                    out.parent.mkdir(exist_ok=True); out.write_bytes(z.read(name))
    shutil.copy2(DEST/'程序/python/LICENSE.txt',DEST/'第三方许可/Python-LICENSE.txt')
    with zipfile.ZipFile(DL/'ffmpeg-release-essentials.zip') as z:
        for name in z.namelist():
            if name.endswith(('/bin/ffmpeg.exe','/bin/ffprobe.exe')):
                (DEST/'程序/ffmpeg'/Path(name).name).write_bytes(z.read(name))
            elif name.endswith(('/LICENSE','/README.txt','/LICENSE.txt')):
                (DEST/'第三方许可'/('FFmpeg-'+Path(name).name)).write_bytes(z.read(name))
    shutil.copy2(HERE/'convert.py',DEST/'程序/convert.py')
    cmd='''@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "%~dp0程序\\python\\python.exe" (
 echo 缺少内置运行环境。请先完整解压ZIP，再双击本文件。
 pause
 exit /b 2
)
"%~dp0程序\\python\\python.exe" -I -B -X utf8 "%~dp0程序\\convert.py"
set "result=%errorlevel%"
echo.
echo 处理结束。请查看“视频输出”和“转换记录”。
pause
exit /b %result%
'''
    (DEST/'开始转换.cmd').write_bytes(cmd.replace('\n','\r\n').encode('utf-8'))
    manifest={p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in DL.iterdir() if p.is_file()}
    (DEST/'构建与验证/下载文件校验.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(DEST)
if __name__=='__main__': build()
