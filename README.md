# 微信跳一跳视觉辅助 · Windows

为电脑微信「跳一跳」制作的独立桌面辅助：截取游戏画面，识别棋子和下一平台，计算并执行鼠标按压。优先瞄准中心，落地后默认等待 3.5 秒领取停留奖励。

历史本机实测单局 **38,624 分**，完成超过 38,594 分的目标，并在结算后确认好友榜第一。该局辅助累计执行 1,366 次按压，期间保留对局暂停并恢复两次。这个结果不代表每次都能命中中心或其他机器上能直接复现。

## 功能

- OpenCV 离线识别默认紫色棋子、平台和满足几何约束的白色中心提示点。
- 分别拟合左右方向按压曲线；转向时按相机中轴修正起点。
- 独立 C# 进程负责按下、计时和释放，减少 Python/Tk 线程对松手时机的影响。
- 检查游戏前台状态、遮挡、窗口尺寸及连续画面稳定性；异常时停止。
- F9 等待本跳落地和停留奖励后暂停；Esc / F8 立即停止。
- 当前代码目标为 **至少 38,595 分**，达到后再次读取分数、保存画面并停止。

通过普通截图和鼠标输入工作，不修改微信客户端、内存或分数数据。程序不会自动分享战绩、点击广告、复活或重开。

## 直接运行 exe（无需安装 Python）

从 [GitHub Releases](https://github.com/Casie-Liu/wechat-jump-assistant/releases/latest) 下载 `WeChatJumpAssistant-Windows-x64.exe`，双击打开，再按下文校准步骤绑定游戏。

单文件版包含 Python、NumPy、OpenCV、Pillow、Tcl/Tk、数字模板和按压计时进程。面向 Windows 10/11 x64，计时进程需要系统自带或已安装的 .NET Framework 4.x。首次启动会解压内置资源，可能稍慢。

exe 版的设置位于 `%LOCALAPPDATA%\WeChatJumpAssistant\settings.json`，日志和截图位于其 `runtime` 子目录；重启会保留校准。程序启动后不会自动开始操作游戏。

Release 同时提供第三方许可证压缩包和 SHA-256 校验文件。exe 未做代码签名。

## 从源码运行

- Windows x64，电脑微信中能正常运行「跳一跳」。
- 64 位 Python 3.11 或以上，含 Tkinter；本机验证版本为 Python 3.14。
- .NET Framework 4.x 的 C# 编译器。`build.cmd` 默认使用 `%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`。

在 PowerShell 中执行：

```powershell
git clone https://github.com/Casie-Liu/wechat-jump-assistant.git
cd wechat-jump-assistant
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\build.cmd
.\start.cmd
```

`build.cmd` 从附带的 `PreciseInput.cs` 构建计时进程。Git 源码不提交预编译 exe；独立版本通过 Releases 分发。`start.cmd` 优先使用本目录的虚拟环境；如果计时进程尚未构建，会先尝试构建。

## 自行打包单文件版

在 Windows x64 和 64 位 Python 3.14 环境下执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build-release.cmd
.\dist\WeChatJumpAssistant-Windows-x64.exe --self-test .\build\self-test.json
```

最后一条命令仅做资源、依赖、识别模块和计时进程的离线自检，不截图或控制微信。构建输出为 `dist/WeChatJumpAssistant-Windows-x64.exe`。打包用的临时资源路径与持久设置路径分离，实现参考 [PyInstaller 运行时文档](https://pyinstaller.org/en/stable/runtime-information.html)。

## 首次校准

1. 打开电脑微信中的「跳一跳」，开始一局，停在第一块平台。
2. 点击辅助界面的「绑定游戏窗口」，只保留一个标题为「跳一跳」的窗口。
3. 点击「检测一次」，核对预览里的棋子底部和下一平台中心；区域错误时重新框选完整游戏窗口，包含顶部工具栏。
4. 「试跳一次」，保持游戏前台。跳短了增加系数，跳远了减小系数，直到落点合适；成功试跳会标记已校准。
5. 点击「开始全自动」。运行时控制面板会最小化。窗口尺寸、缩放或皮肤变化后重新绑定和校准。

程序首次保存配置时会生成 `settings.json`；源码版在项目目录，exe 版在上文用户数据目录。默认系数 1.0，等待 3.5 秒，最多 2,000 次按压；可参考 `settings.example.json`。按压次数不代表成功跳数或得分。

| 按键 | 操作 |
| --- | --- |
| F6 | 检测一次 |
| F7 | 试跳一次 |
| F8 | 开始 / 立即停止 |
| F9 | 等当前跳跃落地并领取停留奖励后暂停 |
| Esc | 立即停止 |

保留对局时优先使用 F9。立即停止或切换前台窗口可能提前松手，导致本跳失败。

## 验证与限制

检测适配曾通过上游 165 张精标图和 1,085 张回归图；分数读取核对过 40 张实图。详细结果与实机记录见 [验证记录](docs/validation.txt)。

本机实测使用默认紫色棋子和 806 × 1503 物理像素游戏窗口。特殊皮肤、移动平台、复杂顶面或遮挡可能使识别失败；换机器后需要重新校准。默认对每个平台都等待 3.5 秒，尚未逐类识别奖励平台。

程序达到目标后会保留仍在进行的对局并停止；要确认好友榜排名，需要在游戏内正常完成本局结算。

## 文件

| 文件 | 用途 |
| --- | --- |
| `jump_assistant.pyw` | Tk 界面、Windows 截图、窗口检查和运行控制 |
| `vision.py` | 图像适配、落点检测和按压计算 |
| `score_reader.py` | 固定数字字体识别，无联网 OCR |
| `PreciseInput.cs` / `precise_input.py` | 独立计时进程与 Python 协议 |
| `build.cmd` / `start.cmd` | 本地构建与启动 |
| `build-release.cmd` / `WeChatJumpAssistant.spec` | 独立单文件构建 |
| `app_paths.py` / `frozen_selftest.py` | 资源路径、持久设置和离线自检 |
| `third_party/` | 上游检测器、数字模板和来源声明 |

运行生成的 `settings.json`、`runtime/` 日志和截图均已加入 `.gitignore`。

## 来源与许可

本项目按 [Apache License 2.0](LICENSE) 分发。图像检测器基于 [zeal-up/wechat_jump_game](https://github.com/zeal-up/wechat_jump_game)，固定来源提交为 `8b6b780dee7a1130baeccf4716de7718a2f6c09d`；上游另致谢 [wangshub/wechat_jump_game](https://github.com/wangshub/wechat_jump_game)。转向策略参考 [zaijiejud/PlayJumpGame](https://github.com/zaijiejud/PlayJumpGame) 的描述。

本地修改包括 Windows 适配、灰色渐变背景修复、近邻平台遮挡修复、受约束的全局中心提示识别、相机中轴修正、独立计时、安全暂停和本机按压曲线。保留的上游声明见 [NOTICE](NOTICE)、[third_party/NOTICE](third_party/NOTICE) 和 [来源说明](third_party/SOURCE.txt)。
