
[README.md](https://github.com/user-attachments/files/33644898/README.md)
# DICOM 转 MP4 工具包

将医院提供的 DICOM 医学影像转换为手机、电脑便于播放的 MP4，方便转院、复诊和与多位医生沟通时查看。

**本地离线转换 · 无需安装运行环境 · 保留原始文件**

## 下载

请前往 **[版本发布与完整工具包下载](https://github.com/yuanxin586878-lang/DICOM-MP4-/releases)**，下载附件中的 `DICOM-MP4-v1.0-Windows-x64.zip`。

如果发布页尚无附件，说明完整工具包还未发布。绿色 `Code → Download ZIP` 以及自动生成的 `Source code (zip)` 只包含源码，不能直接双击运行。

适用系统：Windows 10/11，64 位 x64。原包验证环境为 Windows 11；未在独立 Windows 10 设备上实测。

## 使用方法

1. 完整解压下载的便携 ZIP，不要在压缩软件内部运行。
2. 将医院提供的资料复制到 `原始文件` 文件夹，可以保留原有子目录。
3. 双击 `开始转换.cmd`，等待处理完成。
4. 在 `视频输出` 文件夹查看 MP4；在 `转换记录` 文件夹查看成功、跳过和失败结果。

完整便携版已包含 Python 和 FFmpeg，转换过程无需联网，也不需要输入命令。

## 功能说明

- 按内容识别 DICOM，支持无扩展名、中文文件名及子目录。
- 一个影像对象生成一个 MP4；单帧影像生成 3 秒静态视频。
- 不修改、覆盖原始资料；已有输出视频会跳过。
- 按影像元信息处理常见灰度、窗宽窗位和色彩，转换后校验新视频。
- 支持范围取决于传输语法和像素格式；不保证所有医院设备的 DICOM 都能转换。

**MP4 是有损、8 位的观看副本，不能替代原始 DICOM、专业影像查看器或医学诊断。** 本工具不会自动把多张 CT/MR 切片拼成连续序列，也不会补造影像。

更多细节：[详细使用说明](DICOM%20to%20MP4/README.txt) · [支持范围与验证报告](DICOM%20to%20MP4/支持范围与验证报告.txt)

## 源码与开发

本仓库的项目文件位于 [`DICOM to MP4`](DICOM%20to%20MP4/) 子目录。下面的操作需要自行安装 Python 3.12 x64，适用于开发者；普通用户请下载上面的完整便携版。

在仓库根目录打开 PowerShell，执行：

```powershell
Set-Location 'DICOM to MP4'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

从完整便携版复制 `程序/ffmpeg/ffmpeg.exe` 和 `程序/ffmpeg/ffprobe.exe` 到该项目目录的相同位置，再运行：

```powershell
.\.venv\Scripts\python.exe 程序/convert.py --self-check
.\.venv\Scripts\python.exe 程序/convert.py
```

源码仓库不包含内嵌 Python 或 FFmpeg 可执行文件。源码中的 `开始转换.cmd` 供完整便携版使用。

[转换程序](DICOM%20to%20MP4/程序/convert.py) · [构建与测试源码](DICOM%20to%20MP4/构建与验证/源码/work/build/) · [原许可证](DICOM%20to%20MP4/LICENSE.txt)
