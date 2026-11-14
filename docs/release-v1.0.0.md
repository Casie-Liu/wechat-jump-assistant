# v1.0.0 · Windows x64 独立版

下载 **WeChatJumpAssistant-Windows-x64.exe** 后双击运行，**无需安装 Python、pip 或图像库**。

## 使用

1. 在电脑微信中打开「跳一跳」，开始一局并停在初始平台。
2. 打开 exe，绑定游戏窗口，先「检测一次」和「试跳一次」完成校准。
3. 点击「开始全自动」。**F9** 等当前跳跃落地后安全暂停，**Esc / F8** 立即停止。

优先瞄准平台中心，每次落地默认等 3.5 秒领取停留奖励。目标为至少 **38,595 分**；达到后保存画面并停止，排名以游戏内正常结算为准。

## 本版变化

- 将 Python 3.14.3、NumPy、OpenCV、Pillow、Tcl/Tk、数字模板和独立计时程序打包进单个 exe。
- 将 exe 版配置移至 `%LOCALAPPDATA%\WeChatJumpAssistant\settings.json`；日志和截图位于其 `runtime` 子目录。
- 内置无输入离线自检：`WeChatJumpAssistant-Windows-x64.exe --self-test report.json`。
- 仓库提供打包规格、固定构建依赖和第三方许可证收集脚本。

## 验证范围

在本机 Windows 11 x64 验证：从仅放置 exe 的目录启动，移除 Python 路径及相关环境变量后离线自检通过；确认实际加载包内 Python DLL、数值/图像库、数字模板和计时进程。界面启动、退出和重启后设置保留均已验证。

未重新冲榜；38,624 分是此前源码版本的历史实测成绩。需要 Windows 10/11 x64 和系统自带或已安装的 .NET Framework 4.x；初始系数仍需按机器校准，不能保证每次中心命中。exe 未做代码签名。

## 下载文件

- `WeChatJumpAssistant-Windows-x64.exe`：独立程序。
- `THIRD_PARTY_LICENSES.zip`：运行时及依赖的许可证、声明和版本清单；exe 内也包含这些文本。
- `SHA256SUMS.txt`：上述文件的 SHA-256 校验值。

源代码许可为 Apache-2.0；第三方组件适用各自附带的许可证。
