---
name: boss-candidate-messaging
description: 面向 BOSS 直聘 Windows 桌面端候选人沟通的可组合 pywinauto/UIA 能力集，提供页面导航、岗位精确选择、候选人或会话列表、语义翻页、打开条目、会话检查、已验证发送、文档解析和可选批量编排等独立模块。
---

# BOSS 候选人沟通能力集

本 Skill 是**功能模块集合**，不是固定业务流程。Agent 应根据当前任务选择并组合最少的能力；不得默认把“打开页面→筛选岗位→遍历→发送→翻页”当成唯一执行路径。

所有 UI 操作只调用 `scripts/boss_messages.py` 中已经封装的 pywinauto/UIA 函数。禁止 OCR、截图识别、绝对坐标、列表序号、姓名模糊搜索和临时探索控件。

## 设计原则

- **功能独立**：导航、岗位筛选、列表读取、打开目标、翻页、检查会话、输入发送、文档解析分别可调用。
- **调用方编排**：Agent 根据用户需求决定调用顺序；批处理只是可选的高阶编排器。
- **状态显式**：列表项通过 UIA RuntimeId 传递；打开会话后可独立检查身份、岗位与消息。RuntimeId 仅在该项仍位于当前可见视口时允许点击。
- **视口优先**：BOSS 虚拟列表会在 UIA 树保留屏幕外零矩形项；候选人操作必须先定位列表，再筛选真实可见行，并通过真实滚轮与重叠视口推进。
- **业务值外置**：岗位、联系人、消息正文、消息 ID 和测试数据只来自当前参数或临时文件，禁止写入 Skill。
- **安全提交**：发送能力全文回读后只提交一次，并验证新消息容器；未知状态不重发。

## 初始化与文档模块

```powershell
python "<skill_dir>\scripts\boss_messages.py" inspect
python "<skill_dir>\scripts\boss_messages.py" parse-docs --question-docx "<question.docx>" --answer-docx "<answer.docx>"
```

- `inspect`：只读检查唯一 BOSS 主窗口和 UIA 树。
- `parse-docs`：只读提取两份 DOCX 的当次业务内容，不落盘。
- 缺少任务要求的 DOCX 时返回 `INPUT_DOCUMENT_REQUIRED`，并复制 `assets/templates/` 下的空白模板。

## 页面导航模块

```powershell
python "<skill_dir>\scripts\boss_messages.py" open-surface --surface recommend
python "<skill_dir>\scripts\boss_messages.py" open-surface --surface message
```

只打开顶部业务页面，不选择岗位、不读取列表、不发送消息。

## 岗位筛选模块

```powershell
python "<skill_dir>\scripts\boss_messages.py" select-job --surface recommend --job "<exact_job>"
python "<skill_dir>\scripts\boss_messages.py" select-job --surface message --job "<exact_job>"
```

消息页接受两种安全输入：①页面完整分类文本；②精确岗位短名。短名只在当前 UIA 分类节点中做“岗位名称部分完全相等”解析；唯一命中时选择并回读完整分类，多个地区/薪资分类同名时返回 `JOB_DISAMBIGUATION_REQUIRED` 和候选列表，零命中返回 `JOB_NOT_FOUND`。这不是包含匹配或模糊匹配。推荐页和消息页筛选能力相互独立。

## 推荐候选人模块

### 读取当前已加载候选人

```powershell
python "<skill_dir>\scripts\boss_messages.py" list-candidates
```

返回每张卡片的 UIA RuntimeId、当前状态（`greet` / `continue` / `other`）、可见性和文本。只读取，不打开、不发送。

### 打开一个候选人卡片

```powershell
python "<skill_dir>\scripts\boss_messages.py" open-candidate --runtime-id "<json_array>"
```

只打开指定 RuntimeId 的卡片会话；若卡片仍是“打招呼”，可处理平台默认招呼和“不再显示”，再进入同卡片“继续沟通”。不输入业务消息。

### 推荐列表翻页/懒加载

```powershell
python "<skill_dir>\scripts\boss_messages.py" advance-list --surface recommend
```

固定 `advance_recommendation_page()` 对候选列表末尾 ListItem 调用 UIA ScrollItemPattern。只有出现新卡片签名才返回 `advanced=true`。此能力不查找“打招呼”、不打开卡片、不发送。

## 消息会话模块

### 读取当前已加载会话

```powershell
python "<skill_dir>\scripts\boss_messages.py" list-conversations
```

返回消息列表会话行的 RuntimeId、可见性和预览文本。不打开会话、不发送。 只返回矩形有效且与 BOSS 窗口相交的当前可见行；UIA 树中 `(0,0,0,0)` 的屏幕外虚拟 ListItem 不作为可点击候选人。

### 打开一个会话

```powershell
python "<skill_dir>\scripts\boss_messages.py" open-conversation --runtime-id "<json_array>" [--expected-job "<exact_job>"]
```

只打开指定 RuntimeId 的会话并等待编辑器；回读联系人身份与岗位。不发送。

### 检查当前会话

```powershell
python "<skill_dir>\scripts\boss_messages.py" inspect-chat
```

返回当前联系人、岗位候选、消息容器和编辑器 ID。兼容中文姓名作为一个 Text 或逐字 Text 节点。

### 发消息前定位候选人列表

`batch-message` 在打开任何候选人之前，先完成：岗位精确选择 → “全部”范围 → 从 UIA ListItem 中筛出矩形有效、宽高足够且与 BOSS 窗口相交的会话行。随后在当前可见行的几何中心真实向上滚动，连续两次视口签名不变才确认到达列表顶部；之后再从上到下按重叠视口遍历。禁止直接点击 UIA 树里保留但位于屏幕外、矩形为空的候选人行。

### 消息列表翻页

```powershell
python "<skill_dir>\scripts\boss_messages.py" advance-list --surface message
```

固定 `advance_message_list()` 先定位当前可见候选人会话行，以这些行的矩形交集中心作为滚轮落点，使用真实 `pywinauto.mouse.scroll` 向下滚动 5 格，并以可见视口 RuntimeId 签名变化作为成功证据。滚动距离小于一屏，保留相邻视口重叠，避免漏人；不打开、不发送。

## 当前会话发送模块

将本次消息写入 Skill 目录外的 UTF-8 临时文件：

```powershell
python "<skill_dir>\scripts\boss_messages.py" send-current --message-file "<temporary_utf8.txt>" [--expected-identity "<exact_name>"] [--expected-job "<exact_job>"]
```

该能力只负责当前已经打开的会话：可选校验身份/岗位，激活编辑器，清空草稿，多行用 Shift+Enter，全文回读一致后单次 Enter 提交，再验证编辑器清空和新 `mid-*` 消息容器。

## 消息页批量发送防重账本

消息页批量发送不得把“当前会话预览是否仍显示我方发送文本”作为跨批次防重依据。候选人回复后，预览会变成候选人的最新消息。

每条消息出现新的 `mid-*` 容器并判定 `SENT_VERIFIED` 后，脚本必须立即在 Skill 目录外追加持久化账本。账本键为：

```text
规范化完整岗位 + 精确联系人标题 + 规范化消息 SHA-256
```

后续批次打开会话并回读精确联系人后，必须在按 Enter 前检查该键：命中则记录为 `skipped_already_sent` 并跳过，即使候选人已经回复、会话预览已变化。RuntimeId 只用于同一 UIA 会话和同一运行周期内定位，不作为跨进程身份。账本默认位于用户本地应用数据目录，不写入或打包进 Skill。


## 可选高阶编排器

以下命令只是对上述独立模块的常用组合，不是 Skill 的唯一工作方式：

```powershell
# 推荐页：未沟通候选人的批量打招呼
python "<skill_dir>\scripts\boss_messages.py" batch-greet --job "<exact_job>" --message-file "<file>" --limit N
python "<skill_dir>\scripts\boss_messages.py" batch-greet --job "<exact_job>" --message-file "<file>" --all

# 消息页：现有会话的批量发信息
python "<skill_dir>\scripts\boss_messages.py" batch-message --job "<exact_job>" --message-file "<file>" --limit N
python "<skill_dir>\scripts\boss_messages.py" batch-message --job "<exact_job>" --message-file "<file>" --all
```

调用方也可以自行组合：`open-surface → select-job → list-* → open-* → inspect-chat → send-current → advance-list`，并在任何一步停止、改用另一模块或仅做只读检查。

## 未读问题回复辅助

保留兼容命令：

```powershell
python "<skill_dir>\scripts\boss_messages.py" open-next-unread --job "<exact_job>"
python "<skill_dir>\scripts\boss_messages.py" reply-current --conversation-id "<internal_id>" --reply-file "<temporary_utf8_reply.txt>"
```

Agent 只回答候选人明确提出且回答 DOCX 有依据的问题；不联想，不新增事实或承诺。无依据时返回 `HUMAN_REVIEW_REQUIRED`。

## 消息页发送账本与跨批次防重

消息页批量发送不得依赖“当前预览是否仍显示已发文本”。候选人回复后，列表预览会被新回复覆盖。

- 每条消息通过 `SENT_VERIFIED` 后，立即向 Skill 目录外的运行时账本追加一条记录。
- 账本键为：规范化岗位主体 + 精确联系人标题 + 消息正文 SHA-256。
- 后续批次打开会话并回读联系人/岗位后，在 Enter 提交前查询账本；命中则记为 `skipped_already_sent` 并跳过。
- RuntimeId 和联系人集合只负责同一进程防重；持久账本负责跨进程、续跑以及“候选人回复导致预览变化”的防重。
- 预览文本只可作为同屏快速提示，不得作为跨批次未发送证明。
- 对账本上线前已经发送的记录，打开会话后会精确回查当前消息历史；找到相同消息容器时先补写账本再跳过，避免迁移期重复发送。
- 账本默认保存于当前 Windows 用户的本地应用数据目录，不写入 Skill、不包含消息正文，只保存摘要和消息容器 ID。

## 错误与安全

- `HUMAN_REVIEW_REQUIRED`：回答文档无依据，不发送。
- 高阶全量编排器保留安全上限；原子模块自身只执行一次明确动作。
