"""Generate synthetic fixtures and exercise the isolated embedded Windows runtime."""
from pathlib import Path
import os, sys, json, shutil, subprocess, hashlib, csv, copy, zipfile
from datetime import datetime
import numpy as np
import pydicom
from pydicom.dataset import FileDataset,FileMetaDataset,Dataset
from pydicom.uid import generate_uid,ExplicitVRLittleEndian,ImplicitVRLittleEndian,ExplicitVRBigEndian,DeflatedExplicitVRLittleEndian,RLELossless,JPEGLSLossless,JPEGLSNearLossless,JPEG2000Lossless,JPEG2000,JPEGBaseline8Bit
from pydicom.encaps import encapsulate
from PIL import Image
from io import BytesIO

BUILD=Path(__file__).resolve().parent
BASE=BUILD.parent.parent
PKG=BASE/'work/package/DICOM转MP4工具包'
TEST=BASE/'work'/('移动 测试_'+datetime.now().strftime('%H%M%S'))/'中文 空格/DICOM转MP4工具包'

def fixture(path,n=7,h=65,w=67,bits=16,signed=False):
    meta=FileMetaDataset(); meta.TransferSyntaxUID=ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID='1.2.840.10008.5.1.4.1.1.12.1'; meta.MediaStorageSOPInstanceUID=generate_uid()
    ds=FileDataset(str(path),{},file_meta=meta,preamble=b'\0'*128)
    ds.SOPClassUID=meta.MediaStorageSOPClassUID; ds.SOPInstanceUID=meta.MediaStorageSOPInstanceUID
    ds.PatientName='SYNTHETIC^DO_NOT_LOG'; ds.PatientID='FAKE_NOT_A_PATIENT'
    ds.Rows=h; ds.Columns=w; ds.SamplesPerPixel=1; ds.PhotometricInterpretation='MONOCHROME2'
    ds.BitsAllocated=bits; ds.BitsStored=bits; ds.HighBit=bits-1; ds.PixelRepresentation=int(signed)
    ds.NumberOfFrames=n; ds.FrameTime=40; ds.FrameIncrementPointer=0x00181063
    yy,xx=np.indices((h,w)); frames=[]
    for i in range(n):
        a=((xx*3+yy*2+i*9)%220)+20
        a[(xx-i*3-20)**2+(yy-30)**2<80]=230
        if bits==16: a=a*8
        if signed: a=a-1000
        frames.append(a)
    arr=np.array(frames,dtype=np.int16 if signed else (np.uint8 if bits==8 else np.uint16))
    ds.PixelData=arr.tobytes(); ds.save_as(path,enforce_file_format=True); return ds,arr

def main():
    TEST.mkdir(parents=True,exist_ok=True)
    shutil.copytree(PKG,TEST,dirs_exist_ok=True)
    src=TEST/'原始文件'
    # Repeat runs retain previous outputs to check no-overwrite; fresh run directory is required.
    if list(src.iterdir()): raise RuntimeError('Use a fresh test location')
    (src/'子目录 A').mkdir(); (src/'子目录 B').mkdir()
    cases={}
    def add(name,**kw):
        path=src/name; path.parent.mkdir(parents=True,exist_ok=True)
        d,a=fixture(path,**kw); cases[str(Path(name))]='成功'; return d,a,path
    add('子目录 A/XA_00001'); add('子目录 B/XA_00001')
    add('1.2.840.123456789.000001')
    d,a,p=add('单帧 无扩展名',n=1); del d.FrameTime; d.save_as(p,enforce_file_format=True)
    d,a,p=add('逐帧间隔.dcm'); d.FrameTimeVector=[0,30,50,80,20,60,40]; d.FrameIncrementPointer=0x00181065; d.save_as(p,enforce_file_format=True)
    d,a,p=add('默认帧率'); del d.FrameTime; d.save_as(p,enforce_file_format=True)
    d,a,p=add('MONO1_有符号_窗',signed=True); d.PhotometricInterpretation='MONOCHROME1'; d.RescaleSlope=2; d.RescaleIntercept=-100; d.WindowCenter=500; d.WindowWidth=2000; d.save_as(p,enforce_file_format=True)
    d,a,p=add('负斜率_窗',signed=True); d.RescaleSlope=-2; d.RescaleIntercept=500; d.WindowCenter=500; d.WindowWidth=2000; d.save_as(p,enforce_file_format=True)
    d,a,p=add('VOI_LUT',bits=8); lut=Dataset(); lut.LUTDescriptor=[256,0,8]; lut.LUTData=np.arange(256,dtype=np.uint16).tobytes(); d.VOILUTSequence=[lut]; d.save_as(p,enforce_file_format=True)
    d,a,p=add('中等尺寸120帧',n=120,h=256,w=256,bits=8)
    d,a,p=add('零像素合法DICOM'); d.PixelData=np.zeros_like(a).tobytes(); d.save_as(p,enforce_file_format=True)
    for name,uid,opts in [('RLE',RLELossless,{}),('JPEG_LS',JPEGLSLossless,{}),('JPEG_LS_近无损',JPEGLSNearLossless,{'jls_error':2}),('JPEG2000_无损',JPEG2000Lossless,{}),('JPEG2000_有损',JPEG2000,{'j2k_cr': [4]})]:
        d,a,p=add(name,bits=8,h=64,w=66); d.compress(uid,**opts); d.save_as(p,enforce_file_format=True)
    d,a,p=add('JPEG_基线',bits=8,h=64,w=66)
    fragments=[]
    for frame in a:
        buf=BytesIO(); Image.fromarray(frame).save(buf,format='JPEG',quality=95); fragments.append(buf.getvalue())
    d.PixelData=encapsulate(fragments); d['PixelData'].is_undefined_length=True; d.file_meta.TransferSyntaxUID=JPEGBaseline8Bit; d.save_as(p,enforce_file_format=True)
    for name,uid in [('隐式VR',ImplicitVRLittleEndian),('显式大端',ExplicitVRBigEndian),('Deflate',DeflatedExplicitVRLittleEndian)]:
        d,a,p=add(name)
        d.file_meta.TransferSyntaxUID=uid
        if uid==ExplicitVRBigEndian: d.PixelData=a.astype('>u2').tobytes()
        pydicom.dcmwrite(p,d,enforce_file_format=True,little_endian=(uid!=ExplicitVRBigEndian),implicit_vr=(uid==ImplicitVRLittleEndian))
    d,a,p=add('无DICM前导',bits=8); d.preamble=None; pydicom.dcmwrite(p,d,enforce_file_format=False)
    d,a,p=add('同名冲突'); d,a,p=add('同名冲突.dcm')
    d,a,p=add('RGB彩色',bits=8); rgb=np.stack([a,255-a,a//2],axis=-1); d.SamplesPerPixel=3; d.PhotometricInterpretation='RGB'; d.PlanarConfiguration=0; d.PixelData=rgb.tobytes(); d.save_as(p,enforce_file_format=True)
    from pydicom.pixels import convert_color_space
    d,a,p=add('YBR_FULL彩色',bits=8); rgb=np.stack([a,255-a,a//2],axis=-1); d.SamplesPerPixel=3; d.PhotometricInterpretation='YBR_FULL'; d.PlanarConfiguration=0; d.PixelData=convert_color_space(rgb,'RGB','YBR_FULL').tobytes(); d.save_as(p,enforce_file_format=True)
    d,a,p=add('调色板',bits=8); d.PhotometricInterpretation='PALETTE COLOR'
    for color in ['Red','Green','Blue']:
        setattr(d,color+'PaletteColorLookupTableDescriptor',[256,0,8]); setattr(d,color+'PaletteColorLookupTableData',np.arange(256,dtype=np.uint8).tobytes())
    d.save_as(p,enforce_file_format=True)
    # Legally redistributed pydicom MIT test fixtures; copy only required pixel attributes
    # into our synthetic headers, without copying patient/study metadata.
    with zipfile.ZipFile(BASE/'work/downloads/pydicom-3.0.1-py3-none-any.whl') as z:
        for label,filename in [('JPEG扩展12bit_库测试像素','JPGExtended.dcm'),('JPEG无损SV1_库测试像素','SC_rgb_jpeg_gdcm.dcm')]:
            fixture_ds=pydicom.dcmread(BytesIO(z.read('pydicom/data/test_files/'+filename)))
            d,a,p=add(label,bits=8)
            for key in ['Rows','Columns','SamplesPerPixel','PhotometricInterpretation','BitsAllocated','BitsStored','HighBit','PixelRepresentation','PlanarConfiguration']:
                if key in fixture_ds: d[key]=copy.deepcopy(fixture_ds[key])
                elif key in d: del d[key]
            d.NumberOfFrames=int(getattr(fixture_ds,'NumberOfFrames',1)); d.PixelData=fixture_ds.PixelData; d['PixelData'].is_undefined_length=True
            d.file_meta.TransferSyntaxUID=fixture_ds.file_meta.TransferSyntaxUID; d.save_as(p,enforce_file_format=True)
    d,a,p=add('已有输出'); (TEST/'视频输出/已有输出.mp4').write_bytes(b'EXISTING_DO_NOT_OVERWRITE'); cases['已有输出']='跳过'
    d,a,p=add('截断像素.dcm'); d.PixelData=d.PixelData[:-150]; d.save_as(p,enforce_file_format=True); cases[p.name]='失败'
    d,a,p=add('声明帧数不符'); d.NumberOfFrames=20; d.save_as(p,enforce_file_format=True); cases[p.name]='失败'
    d,a,p=add('损坏压缩'); d.compress(RLELossless); raw=bytearray(d.PixelData); raw[100:200]=b'\xff'*100; d.PixelData=bytes(raw); d.save_as(p,enforce_file_format=True); cases[p.name]='失败'
    d,a,p=add('不支持传输语法'); d.file_meta.TransferSyntaxUID='1.2.840.10008.1.2.4.100'; d.PixelData=encapsulate([b'NOT_MPEG']); d['PixelData'].is_undefined_length=True; d.save_as(p,enforce_file_format=True); cases[p.name]='失败'
    d,a,p=add('无像素显示对象'); del d.PixelData; d.save_as(p,enforce_file_format=True); cases[p.name]='跳过'
    (src/'全零文件').write_bytes(b'\0'*8192); cases['全零文件']='失败'
    (src/'空文件').touch(); cases['空文件']='失败'
    (src/'说明.txt').write_text('这是无关文件，不是DICOM。',encoding='utf-8'); cases['说明.txt']='跳过'
    (src/'损坏头.dcm').write_bytes(b'\0'*128+b'DICM'+b'\xff'*83); cases['损坏头.dcm']='失败'
    before={str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*') if p.is_file()}
    env=os.environ.copy(); env['PATH']=str(Path(os.environ['SystemRoot'])/'System32'); env['PYTHONHOME']='Z:\\NO_GLOBAL_PYTHON'; env['PYTHONPATH']='Z:\\INVALID'; env['PYTHONNOUSERSITE']='1'
    exe=TEST/'程序/python/python.exe'
    check=subprocess.run([str(exe),'-I','-B','-X','utf8',str(TEST/'程序/convert.py'),'--self-check'],env=env,capture_output=True)
    assert check.returncode==0,check.stderr
    (BASE/'work/self-check.json').write_bytes(check.stdout)
    # Invoke actual CMD entry point with pause fed a newline; it calls only the embedded Python.
    proc=subprocess.run([os.environ.get('COMSPEC','cmd.exe'),'/d','/c',str(TEST/'开始转换.cmd')],env=env,input=b'\n',capture_output=True)
    (BASE/'work/test-console.txt').write_bytes(proc.stdout+proc.stderr)
    csvpath=sorted((TEST/'转换记录').glob('*.csv'))[-1]
    rows=list(csv.DictReader(csvpath.open(encoding='utf-8-sig')))
    failures=[]
    for row in rows:
        name=str(Path(row['原文件路径']).relative_to('原始文件'))
        expected=cases[name]
        if not row['处理结果'].startswith(expected): failures.append({'file':name,'expected':expected,'actual':row})
    successful=[r for r in rows if r['处理结果'].startswith('成功')]
    assert len({r['输出路径'].casefold() for r in successful})==len(successful),'Output collision'
    assert (TEST/'视频输出/1.2.840.123456789.000001.mp4').is_file(),'Numeric UID name changed'
    assert (TEST/'视频输出/子目录 A/XA_00001.mp4').is_file()
    assert (TEST/'视频输出/子目录 B/XA_00001.mp4').is_file()
    assert all(r['输出分辨率']=='68x66' for r in successful if r['原始分辨率']=='67x65')
    after={str(p.relative_to(src)):hashlib.sha256(p.read_bytes()).hexdigest() for p in src.rglob('*') if p.is_file()}
    assert before==after,'Source mutated'
    assert (TEST/'视频输出/已有输出.mp4').read_bytes()==b'EXISTING_DO_NOT_OVERWRITE'
    logtext=''.join(p.read_text('utf-8-sig') for p in (TEST/'转换记录').iterdir())
    assert 'DO_NOT_LOG' not in logtext and 'FAKE_NOT_A_PATIENT' not in logtext
    outputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (TEST/'视频输出').rglob('*.mp4')}
    # Existing-output rerun must preserve every output hash.
    again=subprocess.run([str(exe),'-I','-B','-X','utf8',str(TEST/'程序/convert.py')],env=env,capture_output=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in outputs.items())
    result={'os':sys.getwindowsversion()._asdict() if hasattr(sys.getwindowsversion(),'_asdict') else str(sys.getwindowsversion()),'cases':len(cases),'rows':rows,'failures':failures,'source_hash_unchanged':before==after,'existing_outputs_unchanged':True,'isolated_runtime':json.loads(check.stdout),'cmd_exit':proc.returncode,'test_path':str(TEST)}
    (BASE/'work/test-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(cases),'mismatches':len(failures),'failures':failures},ensure_ascii=False,indent=2))
    return bool(failures)
if __name__=='__main__': sys.exit(main())
