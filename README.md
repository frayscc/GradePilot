# AIGrader / AI 阅卷助手

当前进度：**Phase 3 Windows 自动化**。已实现坐标标定、截图、三次 API 请求、观察倒计时、安全填分、提交及下一页视觉确认。试改统计、错判归档和正式自动模式属于后续 Phase。

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

## Phase 2：配置真实题目

启动：

```powershell
aigrader ui
```

点击“新建任务”，选择任务文件保存位置，然后在界面中完成：

1. 考试名称、题号、整题满分、分数步长和模型。
2. 题目文字和/或题目截图。
3. 每空编号、满分、参考答案和得分标准。
4. 每空接受表达、不接受表达、单位、完全匹配及错别字规则。
5. 全题补充评分规则。

编辑停止 600 毫秒后会尝试自动保存。只有配置通过完整校验时才会原子替换任务文件；编辑到一半导致字段暂时不完整时，磁盘上的上一份有效版本不会损坏。选择的题图会复制到任务文件旁的 `<任务名>_assets` 目录，避免原图片移动后任务失效。

整题满分必须与各空满分合计一致，可点击“按各空合计更新满分”。已有任务可通过“打开任务”后点击“编辑任务”继续修改。

## Phase 3：Windows 自动化测试

正式测试前保持浏览器窗口、分辨率和 Windows 显示缩放固定，推荐缩放 100%。启动应用并打开任务：

```powershell
aigrader ui --task path/to/task.json
```

点击“坐标标定”，依次完成：

1. 学生答案区域左上角。
2. 学生答案区域右下角。
3. 分数输入框中心。
4. “提交分数”按钮中心。
5. 阅卷进度数字中心，例如图例中的 `22/1046`。该标记用于安全确认已经进入下一份。

每一步点击捕获后有 3 秒将鼠标移至目标位置。标定保存为任务旁的 `<任务名>.calibration.json`。

设置连续份数和 0～5 秒观察时间后，点击“开始自动化测试（真实提交）”。应用会再次明确提醒该操作会真实提交。默认快捷键：

- F8：安全暂停；当前份不会继续提交。
- F9：继续；从当前份重新截图和评分。
- Ctrl+Alt+Q：紧急停止。
- 鼠标快速移到屏幕左上角：触发 PyAutoGUI failsafe。

每份固定执行：截图 → AI 请求 → JSON/分数验证 → 展示结果 → 观察倒计时 → 确认仍是同一份答案 → 填分 → 最终安全检查 → 提交 → 等待页面变化并稳定。任何 API、JSON、分数、页面、暂停或复核异常都会阻止提交。

API 网络错误最多请求三次，前两次失败后分别等待约 2 秒和 5 秒。结构或分数验证失败不重试，直接暂停。

下一份检测同时观察答案区域和阅卷进度标记，再等待画面稳定。提交按钮的鼠标悬停变化不会被当成换卷证据。它不会因为新答案与上一张相同就直接判定为重复；相同答案时进度数字仍应变化。若完全没有观察到任何页面转换证据，则安全暂停，避免重复提交。

使用 [Phase 3 验收清单](PHASE3_CHECKLIST.md) 在 Windows 智学网页面连续验证 20 份。

## Phase 1：AI 阅卷核心

仍可复制并编辑 [任务示例](examples/task.example.json)，但 Phase 2 日常使用不再要求直接修改 JSON。

### AI 评分结果界面

```powershell
aigrader ui --task examples/task.example.json
```

界面只允许加载任务、选择学生答案图片和执行 Dry Run，显示：

- 各空识别答案
- 各空得分、满分和判分理由
- 总分与摘要
- `need_review` 原因

它不导入网页自动化模块，也不会点击、填分或提交。

### 单张 Dry Run

```powershell
aigrader dry-run --task path/to/task.json --image path/to/answer.png --output output/result.json
```

退出码：`0` 表示验证通过，`2` 表示 AI 主动要求人工复核，`1` 表示 API 或结果验证失败。

### 20 张批量验收

```powershell
aigrader batch --task path/to/task.json --images path/to/answer-images --output output/batch-report.json
```

默认至少要求 20 张图片，并严格串行处理。报告逐张保存识别结果、逐空评分、总分、理由、复核状态、耗时或错误；不会复制或长期保存学生截图。开发冒烟测试可显式加 `--min-images 1`，但不能据此宣称 Phase 1 样本验收通过。

使用 [Phase 1 验收清单](PHASE1_CHECKLIST.md) 逐份人工核对结果。

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

测试覆盖任务结构、评分项合计、Prompt、Provider 请求、结构化结果、评分项映射、分数范围/步长、逐空合计、复核原因、Dry Run 错误隔离以及 Phase 0 提交前安全门。真实 API 准确率、Windows 屏幕和智学网页面属于手工验收项。

## Phase 0 验收记录

使用 [`prototype/PHASE0_CHECKLIST.md`](prototype/PHASE0_CHECKLIST.md) 逐项记录。当前开发机是 macOS，且仓库未提供 API Key、真实学生截图或智学网页面，因此真实 Windows 10 份连续提交尚待用户在目标机验收。

## 当前待验收项

- 用户提供的图例已用于确认“整块学生答案区域”和右侧分数输入/提交区域的产品假设，但未存入仓库。
- 图例不包含完整题干和教师确认的评分规则，因此没有据此猜测参考答案。
- 尚缺 DeepSeek API Key、真实任务配置及至少 20 张答案截图，Phase 1 的真实批量准确率验收待补充样本后执行。
