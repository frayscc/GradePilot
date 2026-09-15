# AIGrader / AI 阅卷助手

当前进度：**Phase 0 Windows 技术验证原型**。没有实现正式 GUI、批量阅卷或无人值守自动模式。

原型用于逐项验证固定区域截图、DeepSeek 视觉识别与结构化评分、坐标输入和显式确认后的提交。所有 AI 输出都会先做硬验证；`need_review`、非法分数、无效 JSON、未显式启用或暂停状态均禁止网页操作。

## 环境

- 正式验证：Windows 10/11 x64，Python 3.12，推荐显示缩放 100%
- 开发检查可在 macOS/Linux 运行，但不能代替 Windows DPI 与智学网页面验收

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,windows]"
Copy-Item .env.example .env
```

在 `.env` 填入 `DEEPSEEK_API_KEY`。密钥文件已被 Git 忽略。默认模型为 DeepSeek 官方[图像理解文档](https://api-docs.deepseek.com/zh-cn/guides/vision/)所列、支持图片输入的 `deepseek-flash`，可通过 `DEEPSEEK_MODEL` 覆盖。

## Phase 0 独立验证入口

### 1. DPI 诊断

分别在 Windows 100%、125%、150% 缩放下运行，并记录屏幕尺寸与鼠标坐标：

```powershell
aigrader-prototype dpi
```

### 2. 固定区域截图

```powershell
aigrader-prototype capture --left 58 --top 166 --width 1316 --height 500 --output prototype/output/answer.png
```

人工打开图片确认边界与网页显示一致。

### 3. DeepSeek Dry Run（绝不移动鼠标）

```powershell
aigrader-prototype grade --image prototype/output/answer.png --question "第16题……" --rubric "每空1分；第1空参考答案……" --max-score 7 --score-step 1 --output prototype/output/result.json
```

输出包含识别答案、逐空得分、总分、理由和 `need_review`。退出码 `2` 表示需要人工复核，任何 API/JSON/分数异常均以非零退出且不会触发自动化。

### 4. 仅填分验证

先把鼠标坐标替换为当前页面实际坐标。`--arm` 是必需的；PyAutoGUI 左上角 failsafe 默认开启。
自动化命令运行期间，F8 暂停、F9 继续、Ctrl+Alt+Q 紧急停止；每个输入动作之间及提交点击前都会重新检查状态。

```powershell
aigrader-prototype automate --result prototype/output/result.json --max-score 7 --score-step 1 --score-x 1510 --score-y 424 --submit-x 1554 --submit-y 475 --arm
```

### 5. 真实提交验证

这是唯一会点击提交按钮的入口，且还要求在终端准确输入 `SUBMIT`：

```powershell
aigrader-prototype automate --result prototype/output/result.json --max-score 7 --score-step 1 --score-x 1510 --score-y 424 --submit-x 1554 --submit-y 475 --arm --submit
```

Phase 0 验收时人工控制执行 10 份：每份先截图、Dry Run、核对结果，再执行填分与提交。遇到 `need_review`、网络错误或结构错误立即停止，不得提交。

## 测试

```powershell
pytest
```

测试覆盖结构化结果、分数范围/步长、逐空合计、复核原因以及提交前安全门。真实屏幕、DeepSeek Key、手写样本和智学网页面属于手工验收项。

## Phase 0 验收记录

使用 [`prototype/PHASE0_CHECKLIST.md`](prototype/PHASE0_CHECKLIST.md) 逐项记录。当前开发机是 macOS，且仓库未提供 API Key、真实学生截图或智学网页面，因此真实 Windows 10 份连续提交尚待用户在目标机验收。
