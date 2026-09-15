# Phase 6 Windows Portable 验收清单

版本：1.0.0
目标：Windows 10/11 x64 无 Python 环境

## 构建产物

- [ ] GitHub Actions 的 Windows job 通过全部测试。
- [ ] 下载的 artifact 名为 `AIGrader-v1.0.0-Windows-x64`。
- [ ] ZIP 内包含 `AIGrader-Windows-x64/AIGrader.exe`、运行库和 `README.txt`。
- [ ] `v*` 标签会创建 GitHub Release 并附加同名 ZIP。

## 便携运行

- [ ] 在未安装 Python 的 Windows x64 机器上完整解压 ZIP。
- [ ] 双击 `AIGrader.exe` 可以打开主界面。
- [ ] 不需要管理员权限，不创建安装项。
- [ ] DPI、截图、全局快捷键及 PyAutoGUI failsafe 正常。

## 用户数据

- [ ] “AI 设置”将 DeepSeek Key 写入 Windows Credential Manager。
- [ ] 新任务默认保存到 `%LOCALAPPDATA%\AIGrader\tasks`。
- [ ] 标定、数据库、日志和异常截图保存在用户数据目录，不写入程序目录。
- [ ] 替换整个程序文件夹升级后，历史任务、试改记录和日志仍存在。
- [ ] 已有外部任务文件仍可手动打开。

## 完整冒烟流程

- [ ] 新建并保存任务。
- [ ] 完成坐标标定。
- [ ] Dry Run 成功。
- [ ] 试改一份并真实提交。
- [ ] F8、F9、Ctrl+Alt+Q 正常。
- [ ] 关闭并重新打开后任务和历史数据库仍存在。

## 验收记录

- GitHub Actions 运行链接：
- Windows 版本 / 是否安装 Python：
- ZIP 文件名 / SHA-256：
- 数据目录：
- 升级保留数据结果：
- 结论与备注：
