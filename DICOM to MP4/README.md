# DICOM 转 MP4 工具包

将医院提供的 DICOM 医学影像转换为手机、电脑便于播放的 MP4，方便转院、复诊或与医生沟通时查看。转换在本地离线完成，保留原始文件。支持 CT、MR、造影等资料中符合支持列表的影像对象；具体以传输语法和像素格式为准。

> MP4 是有损、8 位的观看副本，不能替代原始 DICOM、专业影像查看器或诊断依据。单帧影像会生成 3 秒静态视频；本工具不会把多张 CT/MR 切片自动拼成连续序列，不会用 AI 补帧或补造影像。

## 下载与使用

普通用户请下载仓库 **Releases 附件中的完整便携 ZIP**。GitHub 自动生成的 “Source code (zip)” 和本仓库源码 ZIP 不含 Python、FFmpeg 运行环境，不能直接双击使用。仓库整理时保留的 `DICOM-MP4-original-backup.zip` 就是完整原包，可改名后作为 Release 附件发布。

1. 将完整便携 ZIP 解压到可写、较短的路径，不能在压缩软件里直接运行。
2. 将医院资料复制到 `原始文件`，可保留子目录和 DICOMDIR。
3. 双击 `开始转换.cmd`。
4. 在 `视频输出` 查看 MP4，在 `转换记录` 查看结果、跳过项及失败原因。

完整便携版无需安装 Python、FFmpeg，无需联网。目标系统为 Windows 10/11 x64；原包报告记载实测为 Windows 11 build 22621，未独立实测 Windows 10、实体 U 盘或全部厂商变体。本次仓库整理没有重跑医学影像转换测试。

## 功能与边界

- 按内容识别 DICOM，支持无扩展名、中文、空格和子目录；一个影像对象对应一个 MP4。
- 保留原始资料；已有视频跳过，不覆盖，也不重新验证旧视频。
- 按元信息应用常见灰度、窗宽窗位及彩色显示处理；保留有依据的播放间隔，无可靠依据时明确采用默认 15 fps。
- 新输出使用 FFprobe 核对参数、帧数、时间戳，再经 FFmpeg 完整解码检查。
- 不支持所有 DICOM 变体，例如 MPEG/H.264 封装型 DICOM、私有传输语法和浮点像素等。

完整说明见 [原使用说明](README.txt)、[支持范围与原验证报告](支持范围与验证报告.txt)。这些文件保留原文；其中提到的历史 `构建与验证/测试证据` 仅在完整备份中保留，未纳入源码仓库。

## 隐私

转换过程不上传资料，但这不等于自动脱敏。像素内烧录的姓名、编号、标注仍可能出现在视频中，文件名、路径、错误日志也可能含身份信息。分享前请人工检查影像、视频及日志。

请勿把患者资料、转换视频或运行日志提交到 GitHub。`.gitignore` 已排除工作目录和常见医学文件；它不是脱敏工具，也不会自动移除已提交到 Git 历史的资料。

## 源码目录

```text
程序/convert.py                         实际转换程序
构建与验证/源码/work/build/              原构建脚本、同版转换源码、测试脚本和下载锁
构建与验证/重建说明.txt                   原始重建说明
第三方许可/                              第三方许可、来源和所附源码归档
LICENSE.txt                              原始 GPLv3 许可证正文
requirements.txt                         开发依赖版本
开始转换.cmd                             完整便携版入口
```

所有原自编源码和许可证均按字节保留。仓库保留第三方源码归档（最大的 FFmpeg 源码 ZIP 约 22 MiB），但不提交 FFmpeg/FFprobe EXE 或内嵌 Python。完整便携包保留上述运行库和原有分发内容。

## 开发运行

在 Windows x64 上安装 Python 3.12，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

从完整便携包复制 `程序/ffmpeg/ffmpeg.exe` 和 `ffprobe.exe` 到同名位置（这些文件已被 Git 忽略），然后：

```powershell
.\.venv\Scripts\python.exe 程序/convert.py --self-check
.\.venv\Scripts\python.exe 程序/convert.py
```

构建锁中记录了原下载 URL、版本和 SHA-256；下载器只在开发构建阶段联网，校验不符会拒绝。原脚本的目录关系必须保留：

```powershell
Set-Location '构建与验证/源码/work/build'
python download_dependencies.py
python build.py
```

输出在 `构建与验证/源码/work/package/DICOM转MP4工具包`。原 `build.py` 装配运行库、入口和转换程序，不会自动复刻最终发行包的全部说明、许可和源码归档。重新分发时还须复制根目录说明、`LICENSE.txt`、`第三方许可` 和构建源码，并生成新的文件清单，不能把该中间目录直接称为完整 Release。

`test_portable.py` 使用合成影像、部分第三方测试像素，运行后才可接着执行 `test_display.py`；依赖和顺序见原重建说明。本次保留其原代码，没有宣称重新验证原报告中的转换结果。

## 上传 GitHub

1. 解压 `DICOM-MP4-GitHub-ready.zip`，将里面目录的**内容**上传到新仓库根目录，包括 `.gitignore`；不要只上传 ZIP 本身。
2. 大型运行库已移除，保留文件均小于 25 MiB；可以通过网页上传源码文件，或用 Git 推送。
3. 创建 Release，将完整 `DICOM-MP4-original-backup.zip` 作为附件上传；不要把它提交进仓库。它与原始输入 ZIP 完全一致。
4. 填写发布说明，提醒普通用户下载完整便携附件。

## 许可

自编转换程序、构建及测试源码沿用原包的 **GPL-3.0-or-later** 声明；[LICENSE.txt](LICENSE.txt) 原文未变。第三方组件保留各自许可、NOTICE、来源和已附源码，详见 [组件与来源](第三方许可/组件与来源.txt)。完整包使用 GPL 组件；后续分发须继续遵守对应许可与源码提供要求。本次未对第三方完整许可证合规作法律审查。
