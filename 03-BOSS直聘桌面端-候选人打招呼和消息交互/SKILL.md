---
name: boss-candidate-messaging
description: 面向 BOSS 直聘 Windows 桌面端候选人沟通的 Skill，对外提供四个完整业务能力：根据上传文档回复消息、在消息页面批量发信息、在推荐页面批量打招呼，以及给指定联系人发信息；底层统一使用 pywinauto/UIA，并执行身份核验、防重与发送结果验证。
---

# BOSS 候选人沟通 Skill

本 Skill 的**对外功能颗粒度固定为四个完整业务能力**。Agent 应先判断用户属于哪一种业务需求，再执行对应流程；导航、列表读取、会话检查、翻页和发送等底层函数只作为内部实现细节，不再作为对外功能分类。

所有 BOSS 界面操作必须调用 `scripts/boss_messages.py` 中封装的 pywinauto/UIA 能力。禁止 OCR、截图识别、绝对屏幕坐标、列表序号、姓名模糊搜索和临时猜测控件。

## 使用前检查

```powershell
python "<skill_dir>\scripts\boss_messages.py" inspect
```

要求：Windows 已启动且登录 BOSS直聘桌面端，唯一主窗口的 UIA 树可读。业务参数（岗位、联系人、消息正文、处理数量）必须来自当前任务，禁止写死在 Skill 中。

# 功能一：根据上传文档回消息

## 适用场景

候选人在消息页面提出问题，用户上传了问题规则文档和回答依据文档，要求依据文档回复未读消息。

模板位于：

- `assets/templates/提问招聘者问题篇.docx`
- `assets/templates/回答招聘者问题篇.docx`

## 执行流程

### 1. 解析本次上传文档

```powershell
python "<skill_dir>\scripts\boss_messages.py" parse-docs   --question-docx "<提问招聘者问题篇.docx>"   --answer-docx "<回答招聘者问题篇.docx>"
```

文档必须包含本次实际业务内容。缺失或仍为空白模板时返回 `INPUT_DOCUMENT_REQUIRED`，不得继续回复。

### 2. 打开指定岗位的下一条未读会话

```powershell
python "<skill_dir>\scripts\boss_messages.py" open-next-unread --job "<exact_job>"
```

### 3. 生成并发送有依据的回复

Agent 只能回答候选人明确提出、且回答文档中有直接依据的问题：

- 不联想文档未写明的信息；
- 不新增薪资、岗位、面试、录用或其他承诺；
- 无依据或存在冲突时返回 `HUMAN_REVIEW_REQUIRED`，不发送；
- 将最终回复保存为 Skill 目录外的 UTF-8 临时文件。

```powershell
python "<skill_dir>\scripts\boss_messages.py" reply-current   --conversation-id "<internal_id>"   --reply-file "<temporary_utf8_reply.txt>"
```

发送前必须复核当前会话未切换；发送后必须验证编辑器清空和唯一新 `mid-*` 消息容器。未知状态不得重发。

# 功能二：批量在消息页面发信息

## 适用场景

针对某个精确岗位，在 BOSS“消息”页面向已有会话批量发送同一条信息。

```powershell
# 限定数量
python "<skill_dir>\scripts\boss_messages.py" batch-message   --job "<exact_job>"   --message-file "<temporary_utf8.txt>"   --limit N

# 处理全部符合条件的会话
python "<skill_dir>\scripts\boss_messages.py" batch-message   --job "<exact_job>"   --message-file "<temporary_utf8.txt>"   --all
```

## 固定规则

1. 打开消息页并精确选择岗位；岗位短名只允许唯一的“岗位主体完全相等”匹配，多义时返回 `JOB_DISAMBIGUATION_REQUIRED`。
2. 切换到“全部”，只处理矩形有效、与窗口相交的当前可见会话行；禁止点击 UIA 树中屏幕外或 `(0,0,0,0)` 的虚拟项。
3. 先滚动到列表顶部，再以重叠视口向下推进，使用 RuntimeId 和精确联系人标题识别会话。
4. 每次打开会话后回读联系人和岗位；身份不一致立即停止。
5. 发送前全文回读草稿，只提交一次；验证唯一新消息容器后才记为 `SENT_VERIFIED`。
6. 每次成功后立即写入 Skill 目录外的持久化防重账本。账本键为：规范化岗位 + 精确联系人 + 消息正文 SHA-256。
7. 后续运行命中账本时记为 `skipped_already_sent`。即使候选人回复导致列表预览变化，也不得重复发送。
8. `--all` 仍受脚本安全上限约束；未知发送状态不得自动重试。

# 功能三：批量在推荐页面打招呼

## 适用场景

针对某个精确岗位，在 BOSS“推荐”页面向尚未沟通的候选人批量发送招呼信息。

```powershell
# 限定数量
python "<skill_dir>\scripts\boss_messages.py" batch-greet   --job "<exact_job>"   --message-file "<temporary_utf8.txt>"   --limit N

# 处理全部符合条件的推荐候选人
python "<skill_dir>\scripts\boss_messages.py" batch-greet   --job "<exact_job>"   --message-file "<temporary_utf8.txt>"   --all
```

## 固定规则

1. 打开推荐页并精确选择岗位，不复用消息页的岗位控件假设。
2. 只处理当前状态为 `greet` 的可见候选人卡片；`continue` 和其他状态不得当作未沟通对象。
3. 使用 UIA RuntimeId 和卡片签名定位候选人；RuntimeId 仅在卡片仍处于当前可见视口时有效。
4. 可处理平台默认招呼弹窗及“不再显示”，再进入同一候选人的“继续沟通”状态。
5. 输入自定义招呼前回读候选人身份；发送后验证唯一新消息容器。
6. 推荐列表推进使用 UIA ScrollItemPattern；只有出现新卡片签名才视为推进成功。
7. `--all` 受安全上限约束；未知发送状态不得重试。

# 功能四：给指定人发信息

## 适用场景

用户给出精确联系人姓名和消息正文，要求在 BOSS 消息页面搜索该联系人并发送一条信息。

```powershell
python "<skill_dir>\scripts\boss_messages.py" send-to-contact   --contact-name "<exact_name>"   --message-file "<temporary_utf8.txt>"
```

对应稳定函数：

```python
send_message_to_contact(contact_name, message)
```

## 固定流程

1. 打开 BOSS 消息页。
2. 根据可见会话列表或聊天编辑器的 UIA 边界推导左侧消息栏边界，打开职业筛选栏右侧的联系人搜索按钮；不使用绝对屏幕坐标。
3. 只定位 UIA Edit `搜索姓名/群聊`，输入完整精确姓名。
4. 等待“联系人”结果区出现并打开匹配项；禁止姓名模糊匹配。
5. 回读右侧会话标题，必须与 `contact_name` 完全一致，否则返回 `CONTACT_IDENTITY_MISMATCH`，不发送。
6. 清空草稿并写入完整消息；多行使用 Shift+Enter。
7. 全文回读与参数一致后，只按一次 Enter。
8. 验证编辑器清空及唯一新 `mid-*` 消息容器，返回 `SENT_VERIFIED`。
9. 搜索无结果、会话标题不一致、编辑器不唯一或发送状态未知时立即失败，禁止重发。

# 内部实现能力（技术附录）

以下命令和函数用于实现上述四个业务功能，不作为独立的对外颗粒度：

```text
open-surface / select-job
list-candidates / open-candidate
list-conversations / open-conversation
inspect-chat / send-current
advance-list
open_contact_search()
open_contact_by_exact_name()
semantic_write_and_send()
```

调用方只有在诊断、中断恢复或需要人工复核时，才应直接调用这些底层能力。

# 通用安全约束

- 所有消息正文写入 Skill 目录外的 UTF-8 临时文件。
- 所有业务值来自当前任务参数或上传材料，不写入 Skill。
- 发送前校验当前对象身份；发送后验证唯一新消息容器。
- 每条消息只提交一次；超时、界面切换或结果未知时停止并报告，不自动重发。
- 批量任务必须保留数量上限、视口去重和持久化防重机制。
- `HUMAN_REVIEW_REQUIRED` 表示文档无依据或业务判断不安全，必须交由人工处理。
