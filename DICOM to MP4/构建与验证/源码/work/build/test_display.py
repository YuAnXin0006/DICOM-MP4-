from pathlib import Path
import importlib.util, json, numpy as np
from pydicom.dataset import Dataset
HERE=Path(__file__).resolve().parent; BASE=HERE.parent.parent
spec=importlib.util.spec_from_file_location('converter',HERE/'convert.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
checks=[]
def check(name,actual,expected,tolerance=1):
    assert np.max(np.abs(np.array(actual,dtype=float)-np.array(expected,dtype=float)))<=tolerance,(name,actual,expected)
    checks.append(name)
def mono(signed=False):
    d=Dataset(); d.PhotometricInterpretation='MONOCHROME2'; d.BitsStored=16; d.BitsAllocated=16; d.PixelRepresentation=int(signed)
    return d
d=mono(True); d.RescaleSlope=2; d.RescaleIntercept=-100; d.WindowCenter=500; d.WindowWidth=2000
a=np.array([[-1000,0,300,1000]],dtype=np.int16)
transformed=a.astype(float)*2-100
expected=np.rint(np.clip((transformed-(500-.5))/(2000-1)+.5,0,1)*255)
check('有符号Rescale及DICOM LINEAR窗公式',m.render(a,d,(0,1),[])[:,:,0],expected)
d.PhotometricInterpretation='MONOCHROME1'; check('MONOCHROME1反相',m.render(a,d,(0,1),[])[:,:,0],255-expected)
d.PhotometricInterpretation='MONOCHROME2'; d.RescaleSlope=-2
transformed=a.astype(float)*-2-100
expected=np.rint(np.clip((transformed-(500-.5))/(2000-1)+.5,0,1)*255)
check('负RescaleSlope显示方向',m.render(a,d,(0,1),[])[:,:,0],expected)
d=mono(); check('全序列固定灰度范围',m.render(np.array([[0,500,1000]],dtype=np.uint16),d,(0,1000),[])[:,:,0],[[0,128,255]])
d=mono(); lut=Dataset(); lut.LUTDescriptor=[4,0,8]; lut.LUTData=[0,20,180,255]; d.VOILUTSequence=[lut]
check('VOI LUT',m.render(np.array([[0,1,2,3]],dtype=np.uint16),d,(0,1),[])[:,:,0],[[0,20,180,255]])
d=mono(); d.WindowCenter=0; d.WindowWidth=100; d.VOILUTFunction='SIGMOID'
check('SIGMOID窗中心',m.render(np.array([[0]],dtype=np.int16),d,(0,1),[])[:,:,0],[[128]])
# Complete-decode verification must detect damaged files and parameter mismatches.
testroot=Path(json.loads((BASE/'work/test-results.json').read_text('utf-8'))['test_path'])
m.ROOT=testroot; m.FFMPEG=testroot/'程序/ffmpeg/ffmpeg.exe'; m.FFPROBE=m.FFMPEG.with_name('ffprobe.exe')
p=testroot/'视频输出/子目录 A/XA_00001.mp4'
try: m.verify(p,8,68,66,[.04]*8)
except m.BadInput: checks.append('故意错误帧数被独立校验拒绝')
else: raise AssertionError('Expected wrong-frame-count failure')
corrupt=BASE/'work/corrupt_output.mp4'; data=p.read_bytes(); corrupt.write_bytes(data[:len(data)//2])
try: m.verify(corrupt,7,68,66,[.04]*7)
except m.BadInput: checks.append('截断MP4被校验拒绝')
else: raise AssertionError('Expected damaged-output failure')
# Exercise exact missing-decoder diagnostic without changing installed libraries.
class Missing:
    is_available=False
    missing_dependencies=['synthetic missing decoder test']
m.get_decoder=lambda uid: Missing()
try: m.convert(testroot/'原始文件/JPEG_LS',BASE/'work/no_output.mp4',{})
except m.Unsupported as e:
    assert '缺少解码器' in str(e) and '1.2.840.10008.1.2.4.80' in str(e)
    checks.append('缺少解码器诊断分支（模拟不可用状态）')
else: raise AssertionError('Expected unavailable decoder failure')
(BASE/'work/display-tests.json').write_text(json.dumps({'passed':checks},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False,indent=2))
