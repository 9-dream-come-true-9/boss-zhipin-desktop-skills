---
name: boss-resume-request-collection
description: 面向 BOSS 直聘 Windows 桌面端消息页的可组合 pywinauto/UIA 能力，用于请求简历、发送不消耗平台额度的普通邀请、检测已接收附件、下载原始文件、校验与计算哈希，以及解析 PDF/DOCX。
---

# BOSS 索要与收取简历能力集

本 Skill 是**独立能力模块集合**，不是固定流程。Agent 只按用户当次指令调用最少模块；不得把“索要→等待→预览→下载→解析”固化为必经链路。

## 模块边界

1. `request_resume_by_platform`：消息编辑区上方点击唯一“求简历”，消耗平台次数。
2. `request_resume_by_message`：只发送普通消息，默认逐字为“方便发送一份简历给我吗？”，不点击“求简历”、不消耗次数。
3. `inspect_resume_state`：只读检查是否已求简历、是否有待同意附件请求、是否已有附件气泡。
4. `accept_pending_resume_attachment`：只对候选人发起的唯一待处理附件请求点击一次“同意”；不索要、不发消息、不下载。
5. `download_received_resume`：只下载候选人已经发送的原始附件；不索要、不发消息、不负责预览。
6. `validate_resume_file`：只校验存在性、大小、真实格式、扩展名和 SHA-256。
7. `parse_resume_file`：只解析已经校验的 PDF/DOCX；不修改原件、不执行宏或脚本。
8. `collect_received_resume`：可选编排器，可组合“只读检查→同意待处理附件请求→附件检测→下载→校验→解析”；找不到附件返回 `NOT_RECEIVED`，绝不自动索要。

## 意图路由

- “发消息让他发简历 / 不消耗次数” → `request_resume_by_message`。
- “主动索要 / 点击求简历 / 可以消耗次数” → `request_resume_by_platform`。
- 仅说“要简历” → 只询问一次二选一；选择前零操作。
- “检查/下载/收取简历” → 收取模块；不得触发任何索要。

## 前置定位

所有 UI 操作仅在 BOSS Windows 桌面客户端的“消息”页执行：进入消息页 → 使用顶部岗位筛选器精确选择 `job_ref` → 在筛选后的当前会话列表中按候选人姓名直接定位并打开。

- 顶部岗位精确筛选必须保留。
- 候选人定位使用 BOSS 主 `Document` 的 UIA `TextPattern.DocumentRange`，从完整消息列表文本流中精确查找 `候选人姓名 + 空格 + 岗位短名`。
- `TextPattern` 可读取可见与虚拟化/离屏消息行中的姓名、岗位和消息预览；不得因为 `ListItem.Name` 为空就改为逐行打开聊天标题。
- 精确短语唯一命中后，对该文本范围调用 `ScrollIntoView(True)`；Chromium 虚拟化可能重建列表项，因此滚动后必须重新获取 Document、重新精确查找一次，再由 `GetEnclosingElement()` 包装成 pywinauto `ListItem`。
- 只点击该唯一命中的 UIA `ListItem`；不逐行打开、不设置 8 行上限、不依赖 RuntimeId、不使用 OCR、视觉定位或屏幕绝对坐标。
- 先在当前 `DocumentRange` 完整文本流中搜索；只有零命中时，才查找唯一 UIA TextRange `滚动加载更多` 并调用 `ScrollIntoView(True)`。每次加载后必须重新获取 BOSS 窗口、Document 和 TextPattern，再重新精确搜索；不得逐个打开候选人。
- 加载更多为有界搜索：默认最多 12 轮且总计不超过 45 秒；候选人唯一命中立即停止。出现 `没有更多了`、不存在加载更多范围、加载范围不唯一、TextPattern 文本指纹无变化或达到轮次/时限时必须停步。
- 停止错误分别为：`CANDIDATE_NOT_FOUND_AFTER_UIA_PAGINATION`、`CANDIDATE_NOT_FOUND_IN_UIA_LIST`、`MESSAGE_LOAD_MORE_NOT_UNIQUE`、`MESSAGE_LIST_NO_PROGRESS`、`CANDIDATE_SEARCH_LIMIT_REACHED` 或 `MESSAGE_PAGINATION_FAILED`；不得用 OCR、视觉、列表序号、RuntimeId 或逐项打开补救。
- 多条精确命中返回 `CANDIDATE_NOT_UNIQUE_AFTER_JOB_FILTER` 并停步。

初始化：

```powershell
python "<skill_dir>\scripts\ensure_runtime.py"
python "<skill_dir>\scripts\boss_resume.py" runtime
```

## 平台主动求简历

```powershell
python "<skill_dir>\scripts\boss_resume.py" request-platform --job "<exact_job>" --candidate "<candidate_name>" --request-id "<stable_id>"
```

- 固定入口以唯一消息编辑器 `Group(automation_id="boss-chat-editor-input" / "bosschat-global-input")` 为作用域锚点，解析其正上方操作带；按横向结构选择第一项并回读角色必须为“求简历”。严禁在全窗实时扫描名称为“求简历”的可见 Text，也绝不使用右上角“附件简历”标签。
- 先检查当前会话历史：出现“简历请求已发送”或已有附件气泡时返回 `ALREADY_HANDLED`，不点击。
- 请求账本命中时零操作。
- 用户明确选择平台方式即授权本次额度，不再二次询问。
- 点击入口后，用 UIA 原生属性条件固定定位唯一提示 `Text(title="确定向牛人索取简历吗？")`；再在提示下方的同一弹窗动作带中按“左取消 / 右确定”结构选中右侧操作并回读角色。严禁全窗实时扫描“确定/取消”。原始 PLATFORM 指令只授权确认这个弹窗，不得确认其他提示。
- 点击 `确定` 后必须验证提示消失，并在操作前后的 `mid-*` 差集中找到且只找到一条新增 `简历请求已发送`；否则返回 `COMMIT_UNKNOWN`，禁止重试。
- 提示缺失或重复返回 `CONFIRMATION_DIALOG_NOT_EXACT`；确定/取消不唯一返回 `CONFIRMATION_CONTROLS_NOT_EXACT`。
- 点击后只接受新增“简历请求已发送”消息容器作为成功证据。
- 点击后状态不确定则 `COMMIT_UNKNOWN`，不得重试。

## 普通消息邀请

```powershell
python "<skill_dir>\scripts\boss_resume.py" request-message --job "<exact_job>" --candidate "<candidate_name>" --request-id "<stable_id>" [--message-file "<utf8.txt>"]
```

默认消息逐字为：`方便发送一份简历给我吗？`。只操作编辑器；发送前查请求账本与历史完全相同消息，提交后验证新 `mid-*` 容器。不得点击“求简历”。


## 同意候选人发送附件

```powershell
python "<skill_dir>\scripts\boss_resume.py" accept-pending --job "<exact_job>" --candidate "<candidate_name>" [--request-message-id "<mid-id>"]
```

- 普通消息邀请后，候选人可能先发送“对方想发送附件简历给您，您是否同意”，此时附件尚不能下载。
- `inspect-state` 把同时含“拒绝”和“同意”且其后尚未出现附件消息的 `mid-*` 容器列入 `pending_attachment_requests`。实测同意后旧卡片可能仍可见，后续附件消息是已处理证据，必须防止二次点击。
- 只有唯一待处理请求时，`accept-pending` 才解析该 `mid-*` ListItem 的固定结构：恰好一个文件 Image 与两个横向操作 Text；按“左拒绝 / 右同意”的位置关系选择右侧操作并回读角色。严禁在卡片内实时按名称查找“同意”；多个请求必须由 `request_message_id` 明确选择。
- 点击后只接受新增“点击预览附件简历”消息容器作为 `ACCEPTED_VERIFIED` 证据。结果不确定时进入 `COMMIT_UNKNOWN`，不得重试。
- 该能力独立于普通消息、平台求简历、下载和解析；用户只要求检查时不得自动同意。

## 附件检查与下载

```powershell
python "<skill_dir>\scripts\boss_resume.py" inspect-state --job "<exact_job>" --candidate "<candidate_name>"
python "<skill_dir>\scripts\boss_resume.py" download-received --job "<exact_job>" --candidate "<candidate_name>" --output-dir "<dir>"
```

- 附件证据是包含“点击预览附件简历”的 `mid-*` 消息气泡；该文字仅用于识别附件气泡，不作为单独“预览功能”暴露。
- 下载动作由固定函数直接解析附件卡片结构：先以 `mid-*` ListItem 和唯一“点击预览附件简历”锚点确认目标气泡，再要求同一气泡内恰好存在一个时间 Text、一个预览 Text 和一个文件 Image，并根据这些兄弟节点的固定布局关系命中右上角下载入口。
- 严禁实时扫描名称为“下载 / 下载简历 / 下载附件”的可见控件；也不再按整个附件气泡的宽高比例计算点击位置。BOSS 1.7.4 的下载 glyph 不暴露独立 UIA 节点，因此结构锚点方案使用 DPI 缩放后的节点间距，窗口移动或改变大小后仍须保持有效；结构不唯一或次序异常时安全失败。
- 出现 Windows 原生“下载”保存窗口后，必须先用地址栏（`Alt+D`）导航到 `output_dir`，验证地址工具栏显示该目录，并保持 `Edit(automation_id="1001")` 中的平台原始文件名不变；随后唯一调用一次 `Button(automation_id="1", name^="保存")`。
- 严禁把完整目标路径写进“文件名”输入框；该做法已实测会静默落到桌面。严禁再搜索桌面、复制或搬运文件作为补救。只有原件直接出现在 `output_dir` 才算下载成功。
- 下载前后比较输出目录快照，只接受一个新 PDF/DOCX 原文件。多个附件必须由 `attachment_message_id` 明确选择。
- 不点击右上角“附件简历”标签，不把简历预览当下载成功，不保存截图。

## 文件校验与解析

```powershell
python "<skill_dir>\scripts\boss_resume.py" validate-file --file "<path>"
python "<skill_dir>\scripts\boss_resume.py" parse-file --file "<path>"
python "<skill_dir>\scripts\boss_resume.py" collect --job "<exact_job>" --candidate "<candidate_name>" --output-dir "<dir>"
```

PDF 必须以 `%PDF-` 开头；DOCX 必须为 ZIP 且含 `[Content_Types].xml` 与 `word/document.xml`。先 SHA-256 后解析。相同 SHA-256 原件不得重复保存。

## 批量

`request_resumes(job_ref, candidate_refs, mode, request_id)` 只在 mode 明确时执行。同批默认统一模式；混合方式必须给出候选人→模式映射。平台提交一旦 `COMMIT_UNKNOWN` 立即停止批次。

## 安全约束

- 禁止 OCR、截图识别、私有接口、绝对坐标、列表序号和模糊姓名匹配；岗位筛选后使用候选人姓名精确匹配。

- 不关闭、重启或退出 BOSS。

- 原子提交只调用一次；未知状态不重试。

  运行状态与账本在 Skill 目录外的 `%LOCALAPPDATA%\CyberNuwa\boss-resume-request-collection`。

## 返回值

输出必须通过 `schemas/ActionReceipt.schema.json`、`BatchReceipt.schema.json` 或 `ResumeReceipt.schema.json` 校验。仅 `PLATFORM + REQUESTED_VERIFIED` 可令 `quota_consumed=true`。
