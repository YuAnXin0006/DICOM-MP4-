"""Offline DICOM viewing derivatives. No network, no diagnostic interpretation."""
from __future__ import annotations
import csv, json, math, os, sys, subprocess, tempfile, shutil, hashlib, logging, warnings
from pathlib import Path
from datetime import datetime
from copy import copy
from fractions import Fraction
import numpy as np
import pydicom
from pydicom.pixels import iter_pixels, apply_modality_lut, apply_voi_lut, apply_color_lut, get_decoder
from pydicom.errors import InvalidDicomError

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = ROOT / '程序' / 'ffmpeg' / 'ffmpeg.exe'
FFPROBE = FFMPEG.with_name('ffprobe.exe')
DEFAULT_FPS = 15.0
FIELDS = ['原文件路径','输出路径','处理结果','错误原因','传输语法','原始帧数','输出帧数','时长秒','帧率','帧率来源','原始分辨率','输出分辨率','显示处理','告警']
SUPPORTED = ['1.2.840.10008.1.2','1.2.840.10008.1.2.1','1.2.840.10008.1.2.1.99','1.2.840.10008.1.2.2','1.2.840.10008.1.2.5','1.2.840.10008.1.2.4.50','1.2.840.10008.1.2.4.51','1.2.840.10008.1.2.4.57','1.2.840.10008.1.2.4.70','1.2.840.10008.1.2.4.80','1.2.840.10008.1.2.4.81','1.2.840.10008.1.2.4.90','1.2.840.10008.1.2.4.91']

class BadInput(Exception): pass
class Unsupported(Exception): pass

def run(args):
    p = subprocess.run([str(x) for x in args], capture_output=True, creationflags=0x08000000)
    if p.returncode:
        raise BadInput('FFmpeg/FFprobe 失败: ' + p.stderr.decode('utf-8','replace')[-1800:])
    return p.stdout

def identify(path):
    # Read by content. force is allowed only with strong DICOM structural evidence.
    zero = True
    with path.open('rb') as f:
        while chunk := f.read(1024*1024):
            if chunk.strip(b'\0'): zero = False; break
    if zero: raise BadInput('全零文件' if path.stat().st_size else '空文件（0字节）')
    try: ds = pydicom.dcmread(path)
    except InvalidDicomError:
        try: ds = pydicom.dcmread(path, force=True)
        except Exception as e: raise BadInput('疑似损坏或非标准 DICOM：' + type(e).__name__)
        if not (getattr(ds,'SOPClassUID',None) and getattr(ds,'SOPInstanceUID',None)):
            if path.suffix.lower() in ('.dcm','.dicom'):
                raise BadInput('损坏或无法确认的 DICOM（缺少有效头及对象标识）')
            return None
    except Exception as e: raise BadInput('DICOM 读取损坏：' + type(e).__name__ + ': ' + str(e)[:500])
    if not (getattr(ds,'SOPClassUID',None) and getattr(ds,'SOPInstanceUID',None)):
        # DICOMDIR may identify the directory object only in file meta.
        if not (getattr(ds.file_meta,'MediaStorageSOPClassUID',None) and getattr(ds.file_meta,'MediaStorageSOPInstanceUID',None)):
            raise BadInput('DICOM头损坏或缺少对象标识，不能当作正常无像素对象跳过')
    return ds

def frame_context(ds, i):
    ctx = copy(ds)
    groups = []
    if 'SharedFunctionalGroupsSequence' in ds: groups.append(ds.SharedFunctionalGroupsSequence[0])
    if 'PerFrameFunctionalGroupsSequence' in ds:
        if len(ds.PerFrameFunctionalGroupsSequence) != int(getattr(ds,'NumberOfFrames',1)):
            raise BadInput('逐帧功能组数量与声明帧数不符，未补帧')
        groups.append(ds.PerFrameFunctionalGroupsSequence[i])
    for g in groups:
        for seq in ('PixelValueTransformationSequence','FrameVOILUTSequence'):
            if seq in g:
                for elem in g[seq][0]: ctx[elem.tag] = elem
    return ctx

def timing(ds, n, notes):
    if n == 1: return [1/25]*75, '原始仅1帧，延长显示3秒；静态MP4（25fps）'
    if 'FrameTimeVector' in ds:
        v = [float(x) for x in ds.FrameTimeVector]
        if len(v)==n and abs(v[0])<1e-6 and all(math.isfinite(x) and x>0 for x in v[1:]):
            notes.append('逐帧间隔保留；最后一帧停留时长无下一帧依据，沿用前一间隔')
            return [x/1000 for x in v[1:]]+[v[-1]/1000], 'FrameTimeVector（最后间隔沿用）'
        notes.append('FrameTimeVector 无效或数量不符，改用后续时间依据')
    if 'PerFrameFunctionalGroupsSequence' in ds:
        try:
            from pydicom.valuerep import DT
            ts=[DT(g.FrameContentSequence[0].FrameAcquisitionDateTime) for g in ds.PerFrameFunctionalGroupsSequence]
            diffs=[(b-a).total_seconds() for a,b in zip(ts,ts[1:])]
            if len(ts)==n and all(math.isfinite(x) and x>0 for x in diffs):
                notes.append('逐帧采集时间差保留；最后停留沿用前一间隔')
                return diffs+[diffs[-1]], '逐帧 FrameAcquisitionDateTime（最后间隔沿用）'
        except (AttributeError,ValueError,TypeError,IndexError): pass
    for tag, divisor in [('FrameTime',1000),('RecommendedDisplayFrameRate',None),('CineRate',None)]:
        try:
            x=float(getattr(ds,tag)); d=x/divisor if divisor else 1/x
            if math.isfinite(d) and d>0:
                if tag!='FrameTime': notes.append('使用标记的显示/电影帧率，非逐帧实测采集时间')
                return [d]*n, tag
        except (AttributeError,ValueError,TypeError,ZeroDivisionError): pass
    notes.append('无可靠时间信息，采用默认15fps；不是原始帧率')
    return [1/DEFAULT_FPS]*n, '默认15fps（非原始帧率）'

def render(a, ctx, limits, notes):
    photo=str(ctx.PhotometricInterpretation)
    if photo in ('MONOCHROME1','MONOCHROME2'):
        b=apply_modality_lut(a,ctx)
        has_voi='VOILUTSequence' in ctx or ('WindowCenter' in ctx and 'WindowWidth' in ctx)
        if has_voi:
            b=apply_voi_lut(b,ctx)
            if 'VOILUTSequence' in ctx:
                lo,hi=0., float(2**int(ctx.VOILUTSequence[0].LUTDescriptor[2])-1)
            else:
                if 'ModalityLUTSequence' in ctx: lo,hi=0.,float(2**int(ctx.ModalityLUTSequence[0].LUTDescriptor[2])-1)
                else:
                    bits=int(ctx.BitsStored); signed=int(ctx.PixelRepresentation)
                    lo,hi=(-2**(bits-1),2**(bits-1)-1) if signed else (0,2**bits-1)
                    slope=float(getattr(ctx,'RescaleSlope',1)); intercept=float(getattr(ctx,'RescaleIntercept',0))
                    # pydicom windowing preserves the signed output range for negative slope.
                    lo,hi=lo*slope+intercept,hi*slope+intercept
        else: lo,hi=limits
        b=np.zeros(b.shape,dtype=np.uint8) if hi==lo else np.rint(np.clip((b-lo)/(hi-lo),0,1)*255).astype(np.uint8)
        if photo=='MONOCHROME1' or (photo=='MONOCHROME2' and str(getattr(ctx,'PresentationLUTShape','')).upper()=='INVERSE'): b=255-b
        return np.repeat(b[...,None],3,axis=2)
    if photo=='PALETTE COLOR':
        a=apply_color_lut(a,ctx)
        if a.dtype==np.uint16: a=np.rint(a/257).astype(np.uint8)
    elif photo not in ('RGB','YBR_FULL','YBR_FULL_422','YBR_RCT','YBR_ICT'):
        raise Unsupported('不支持的光度解释：'+photo)
    if a.ndim!=3 or a.shape[2]!=3: raise Unsupported('不支持的彩色通道形状')
    if a.dtype!=np.uint8:
        if int(getattr(ctx,'PixelRepresentation',0)): raise Unsupported('有符号彩色像素未实现')
        a=np.rint(a.astype(float)/(2**int(ctx.BitsStored)-1)*255).clip(0,255).astype(np.uint8)
    return np.ascontiguousarray(a)

def verify(path,n,w,h,durations):
    # Independently probe and decode EVERY output packet/frame. Never trust encoder exit alone.
    probe=json.loads(run([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',path]))
    streams=probe['streams']
    if len(streams)!=1: raise BadInput('输出包含非预期流或音轨')
    s=streams[0]
    if s['codec_name']!='h264' or s.get('pix_fmt')!='yuv420p': raise BadInput('输出编码/像素格式校验失败')
    if (int(s['width']),int(s['height']))!=(w,h): raise BadInput('输出尺寸校验失败')
    if int(s.get('nb_read_frames',-1))!=n: raise BadInput('输出帧数校验失败')
    frames=json.loads(run([FFPROBE,'-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time,pkt_duration_time,duration_time','-of','json',path]))['frames']
    if len(frames)!=n: raise BadInput('逐帧核对失败')
    pts=[float(f['best_effort_timestamp_time']) for f in frames]
    expected=np.cumsum([0.]+durations[:-1])
    if max(abs(x-y) for x,y in zip(pts,expected))>0.002: raise BadInput('输出逐帧时间戳不符（容差2ms）')
    actual=float(s.get('duration',probe['format']['duration']))
    if abs(actual-sum(durations))>max(.01,sum(durations)*.001): raise BadInput(f'输出时长校验失败：{actual:.6f} / {sum(durations):.6f}')
    run([FFMPEG,'-hide_banner','-v','error','-xerror','-err_detect','explode','-i',path,'-map','0:v:0','-an','-f','null','-'])
    return actual

def convert(path,out,row):
    notes=[]
    ds=identify(path)
    if ds is None: row['处理结果']='跳过：无关或无法识别的文件'; return
    pixels=[k for k in ('PixelData','FloatPixelData','DoubleFloatPixelData') if k in ds]
    if not pixels: row['处理结果']='跳过：DICOM无像素数据（索引/显示设置等）'; return
    if 'FloatPixelData' in ds or 'DoubleFloatPixelData' in ds: raise Unsupported('浮点像素对象暂不支持，未转换')
    if not hasattr(ds.file_meta,'TransferSyntaxUID'):
        # Raw datasets often lack meta information: infer only uncompressed encoding from reader.
        implicit,little=ds.original_encoding[:2]
        if implicit is None or little is None: raise Unsupported('缺少传输语法，不能安全推断')
        uid='1.2.840.10008.1.2' if implicit else ('1.2.840.10008.1.2.1' if little else '1.2.840.10008.1.2.2')
        ds.file_meta.TransferSyntaxUID=uid; notes.append('无文件元信息；按DICOM读取器检测的未压缩编码推断传输语法')
    uid=str(ds.file_meta.TransferSyntaxUID); row['传输语法']=uid
    if uid not in SUPPORTED: raise Unsupported('不支持的传输语法：'+uid+'；未解码、未补造')
    decoder=get_decoder(uid)
    if not decoder.is_available: raise Unsupported('缺少解码器：'+uid+'；'+ '; '.join(decoder.missing_dependencies))
    n=int(getattr(ds,'NumberOfFrames',1)); h=int(ds.Rows); w=int(ds.Columns)
    if n<=0 or min(h,w)<=0: raise BadInput('无效的帧数或尺寸')
    row['原始帧数']=n; row['原始分辨率']=f'{w}x{h}'
    if 'PresentationLUTSequence' in ds: raise Unsupported('自定义 Presentation LUT 暂不支持，避免错误显示')
    if getattr(ds,'LossyImageCompression','00')=='01': notes.append('原始DICOM标记为有损压缩')
    if getattr(ds,'BurnedInAnnotation','')=='YES': notes.append('原始像素可能含烧录文字；视频保留像素内文字')
    if any(k in ds for k in ('ShutterShape',)): notes.append('未应用显示遮片；保留完整像素范围')
    if 'PixelAspectRatio' in ds and list(ds.PixelAspectRatio)!=[1,1]: notes.append('原始像素纵横比非1:1；保留像素矩阵不拉伸，MP4按方形像素显示')
    if any(tag.group & 0xFF00 == 0x6000 for tag in ds.keys()): notes.append('覆盖层未合成；保留原始图像像素')
    durations,source=timing(ds,n,notes)
    if any(d<.001 or d>3600 for d in durations): raise Unsupported('时间间隔超出工具支持范围1ms至3600s，未强改速度')
    target_n=len(durations)
    row['帧率来源']=source; row['帧率']=f'{target_n/sum(durations):.8g}'+('（可变，平均）' if max(durations)-min(durations)>1e-7 else '')
    if n==1: notes.append('原始仅1帧，延长显示；不是动态录像')
    photo=str(ds.PhotometricInterpretation)
    # A preliminary pass checks exact frame count and establishes ONE global grayscale range.
    lo,hi=math.inf,-math.inf; count=0; blank_count=0
    for i,a in enumerate(iter_pixels(ds,raw=False,allow_excess_frames=False)):
        if i>=n: raise BadInput('实际帧数超过声明值，未静默忽略')
        if a.shape[:2]!=(h,w): raise BadInput('帧尺寸不一致')
        if not np.isfinite(a).all(): raise BadInput('存在非有限像素值')
        if not np.any(a): blank_count+=1
        ctx=frame_context(ds,i)
        if photo.startswith('MONOCHROME'):
            b=apply_modality_lut(a,ctx)
            valid=b
            if 'PixelPaddingValue' in ctx:
                p=float(ctx.PixelPaddingValue); q=float(getattr(ctx,'PixelPaddingRangeLimit',p))
                mask=(a<min(p,q))|(a>max(p,q)); valid=b[mask]
            if valid.size: lo=min(lo,float(valid.min())); hi=max(hi,float(valid.max()))
        count+=1
    if count!=n: raise BadInput(f'声明{n}帧，实际{count}帧；未删除或补齐')
    # Check native payload length independently, rather than accepting truncated/excess frames.
    if not ds.file_meta.TransferSyntaxUID.is_compressed:
        from pydicom.pixels.utils import get_expected_length
        size=get_expected_length(ds); actual=len(ds.PixelData)
        if actual not in (size,size+(size%2)): raise BadInput(f'像素数据长度不符：实际{actual}，应为{size}（允许偶数字节填充）；疑似缺失/多余资料')
    else:
        from pydicom.encaps import generate_frames
        actual=sum(1 for _ in generate_frames(ds.PixelData,number_of_frames=n))
        if actual!=n: raise BadInput(f'压缩片段解析得到{actual}帧，声明{n}帧；未补齐')
    if blank_count: notes.append(f'{blank_count}帧像素全为0：原样保留，仅提示复核，不据此判定损坏')
    if not math.isfinite(lo): lo,hi=0.,1.
    first=frame_context(ds,0)
    row['显示处理']=('Modality LUT/Rescale + 首组VOI LUT/窗宽窗位（如存在）' if photo.startswith('MONO') else '彩色解码转RGB')
    if photo.startswith('MONO') and not ('VOILUTSequence' in first or ('WindowCenter' in first and 'WindowWidth' in first)):
        notes.append(f'无VOI：使用全对象统一显示范围{lo:g}至{hi:g}（排除已声明padding）；未逐帧自动拉伸')
    if photo=='MONOCHROME1': notes.append('MONOCHROME1反相显示')
    ew=w+w%2; eh=h+h%2
    if (ew,eh)!=(w,h): notes.append(f'仅右侧/底部黑色补边：{w}x{h}→{ew}x{eh}，无拉伸裁切')
    row['输出分辨率']=f'{ew}x{eh}'; row['告警']='；'.join(notes)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dicom_work_',dir=out.parent) as td:
        td=Path(td); tempout=td/'result.mp4'
        common=['-an','-map_metadata','-1','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-vf',f'pad={ew}:{eh}:0:0:black,setsar=1','-bf','0','-video_track_timescale','1000000','-movflags','+faststart',tempout]
        variable=max(durations)-min(durations)>1e-7
        if variable:
            listing=[]
            for i,a in enumerate(iter_pixels(ds,raw=False,allow_excess_frames=False)):
                rgb=render(a,frame_context(ds,i),(lo,hi),notes)
                name=f'f{i:08d}.ppm'
                with (td/name).open('wb') as f: f.write(f'P6\n{w} {h}\n255\n'.encode()+rgb.tobytes())
                listing.extend([f"file '{name}'",'option framerate 1000000',f'duration {durations[i]:.9f}'])
            (td/'frames.txt').write_text('\n'.join(listing)+'\n',encoding='ascii')
            # setts sets the final MP4 sample duration without adding a duplicate frame.
            bsf=f'setts=duration=if(eq(N\\,{n-1})\\,{durations[-1]:.9f}/TB\\,DURATION)'
            run([FFMPEG,'-hide_banner','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',td/'frames.txt','-fps_mode','vfr','-enc_time_base','1:1000000','-bsf:v',bsf]+common)
        else:
            args=[str(x) for x in [FFMPEG,'-hide_banner','-v','error','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r',f'{1/durations[0]:.12g}','-i','pipe:0']+common]
            with (td/'encoder.log').open('wb') as err:
                proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=err,creationflags=0x08000000)
                try:
                    for i,a in enumerate(iter_pixels(ds,raw=False,allow_excess_frames=False)):
                        rgb=render(a,frame_context(ds,i),(lo,hi),notes).tobytes()
                        for _ in range(target_n if n==1 else 1): proc.stdin.write(rgb)
                    proc.stdin.close()
                    code=proc.wait()
                    if code: raise BadInput('编码失败：'+(td/'encoder.log').read_text('utf-8',errors='replace')[-1800:])
                except BaseException:
                    proc.kill(); proc.wait(); raise
        actual=verify(tempout,target_n,ew,eh,durations)
        # Windows rename fails atomically if target appeared in the meantime.
        tempout.rename(out)
    row['输出帧数']=target_n; row['时长秒']=f'{actual:.6f}'; row['处理结果']='成功（完整解码和参数核验通过）'

def main():
    if '--self-check' in sys.argv:
        report={'python':sys.version,'executable':sys.executable,'isolated':sys.flags.isolated,'path':sys.path,'pydicom':pydicom.__version__,'numpy':np.__version__,'decoders':{uid:{'available':get_decoder(uid).is_available,'plugins':get_decoder(uid).available_plugins} for uid in SUPPORTED},'ffmpeg':run([FFMPEG,'-version']).decode().splitlines()[0]}
        print(json.dumps(report,ensure_ascii=False,indent=2)); return 0
    src=ROOT/'原始文件'; dst=ROOT/'视频输出'; logs=ROOT/'转换记录'
    for p in (src,dst,logs): p.mkdir(exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f'); csvpath=logs/f'转换清单_{stamp}.csv'
    logging.getLogger('pydicom').setLevel(logging.CRITICAL)
    counts={'成功':0,'跳过':0,'失败':0}
    files=sorted(p for p in src.rglob('*') if p.is_file())
    # Plan names before converting: prevent foo and foo.dcm from claiming the same output.
    targets={}; names={}
    for path in files:
        rel=path.relative_to(src)
        basename=path.stem if path.suffix.lower() in ('.dcm','.dicom','.ima') else path.name
        base=dst/rel.parent/(basename+'.mp4')
        key=str(base).casefold(); names.setdefault(key,[]).append(path); targets[path]=base
    for group in names.values():
        if len(group)>1:
            for path in group:
                targets[path]=targets[path].with_name(targets[path].stem+'__'+hashlib.sha256(path.name.encode('utf-8')).hexdigest()[:12]+'.mp4')
    print('完全离线转换；请保留原始 DICOM。MP4仅供观看。',flush=True)
    print(f'发现 {len(files)} 个文件。',flush=True)
    with csvpath.open('w',encoding='utf-8-sig',newline='') as cf, (logs/f'详细日志_{stamp}.jsonl').open('w',encoding='utf-8') as lf:
        writer=csv.DictWriter(cf,fieldnames=FIELDS); writer.writeheader()
        for index,path in enumerate(files,1):
            out=targets[path]; row={k:'' for k in FIELDS}; row['原文件路径']=str(path.relative_to(ROOT)); row['输出路径']=str(out.relative_to(ROOT))
            print(f'[{index}/{len(files)}] {path.relative_to(src)}',flush=True)
            try:
                if out.exists(): row['处理结果']='跳过：已有输出（未覆盖，未重新验证）'
                else:
                    with warnings.catch_warnings(record=True) as ws:
                        warnings.simplefilter('always'); convert(path,out,row)
                    if ws: row['告警']+=f'；DICOM读取/解码库产生{len(ws)}条告警（可能涉及非标准元信息、局部缺失或可疑帧；未删除、补齐或宣称修复。为避免身份字段泄漏不展开字段值，请用原始DICOM复核）'
            except Unsupported as e: row['处理结果']='失败：不支持的格式或解码器'; row['错误原因']=str(e)
            except (BadInput,Exception) as e:
                row['处理结果']='失败：全零文件' if str(e)=='全零文件' else ('失败：空文件' if str(e).startswith('空文件') else '失败：损坏、解码或校验异常')
                row['错误原因']=type(e).__name__+': '+str(e)[:2400]
            category='成功' if row['处理结果'].startswith('成功') else ('跳过' if row['处理结果'].startswith('跳过') else '失败')
            counts[category]+=1
            # Prevent formula evaluation when opening CSV files whose original names are untrusted.
            writer.writerow({k:("'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()}); cf.flush()
            lf.write(json.dumps({'时间':datetime.now().isoformat(),**row},ensure_ascii=False)+'\n'); lf.flush()
            print('  '+row['处理结果']+('：'+row['错误原因'] if row['错误原因'] else ''),flush=True)
        lf.write(json.dumps({'汇总':counts},ensure_ascii=False)+'\n')
    print(f"结束：成功 {counts['成功']}，跳过 {counts['跳过']}，失败 {counts['失败']}。",flush=True)
    print('中文清单：'+str(csvpath),flush=True)
    return 1 if counts['失败'] else 0

if __name__=='__main__':
    try: sys.exit(main())
    except KeyboardInterrupt: print('用户中止；尚未完成的视频不计为成功。'); sys.exit(130)
    except Exception as e: print('工具启动失败：'+type(e).__name__+': '+str(e)); sys.exit(2)
