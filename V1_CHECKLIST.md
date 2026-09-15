# AIGrader V1.0 收尾验收清单

## API 设置

- [ ] “AI 设置”可保存默认模型和 Base URL。
- [ ] Windows API Key 可在 Credential Manager 的 `AIGrader.DeepSeek` 中找到。
- [ ] `settings.json` 和任务 JSON 均不包含 API Key。
- [ ] “测试连接”能明确显示成功或错误。

## 人工复核提交

- [ ] `need_review` 后自动化不填分、不提交。
- [ ] 人工总分不符合范围或步长时不触碰页面。
- [ ] “人工提交并继续”填写分数、提交并确认下一页。
- [ ] 下一页未确认时停止，不自动重试。
- [ ] 试改和自动模式的复核结果、正确分数、原因及提交状态均写入数据库。

## 规则与任务设置

- [ ] 修改规则后规则版本增加，旧试改结果不能解锁新规则自动模式。
- [ ] 观察时间、连续上限/无限制和三组快捷键重启后保持。
- [ ] 旧版任务 JSON 可正常打开，并使用 1 秒、100 份、F8/F9/Ctrl+Alt+Q 默认值。

## GitHub 主分支

- [ ] `main` 指向 V1.0 最新提交，不再包含原先无关历史内容。
- [ ] Windows Actions 测试和 Portable 构建成功。
- [ ] Artifact 包含 `AIGrader.exe` 和完整 `_internal` 运行库。
