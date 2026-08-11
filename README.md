# BOSS 直聘 Windows 桌面端 Skill 合集

这是一组面向支持本地 Skill 或工具扩展机制的 AI 智能体的 Windows 桌面自动化能力，通过 `pywinauto` 与 Windows UI Automation（UIA）操作 BOSS 直聘桌面客户端。

仓库包含四个彼此独立、可组合使用的 Skill。每个 Skill 都以自己的 `SKILL.md` 作为完整行为规范，并附带完成任务所需的脚本、Schema、模板或运行时资源。

> [!IMPORTANT]
> 本项目是非官方开源项目，与 BOSS 直聘及其运营主体不存在隶属、合作、赞助或认可关系。“BOSS 直聘”及相关名称、标识的权利归其权利人所有。使用者应自行确认其使用方式符合适用法律、组织政策和平台最新协议，并仅操作自己有权使用的账号与数据。

## 包含的 Skill

| Skill | 标识符 | 主要能力 |
| --- | --- | --- |
| [岗位发布](./01-BOSS直聘桌面端-岗位发布/) | `boss-job-publishing` | 填写、回读核验并发布 BOSS 直聘实习岗位，以及核对结果不确定的提交 |
| [候选人初评分](./02-BOSS直聘桌面端-候选人初评分/) | `boss-candidate-scoring` | 读取指定岗位要求，仅从“消息”入口采集候选人，并进行有证据边界的初步评分 |
| [候选人打招呼和消息交互](./03-BOSS直聘桌面端-候选人打招呼和消息交互/) | `boss-candidate-messaging` | 岗位筛选、候选人和会话读取、语义翻页、会话检查、已验证消息发送与批量编排 |
| [索要与收取简历](./04-BOSS直聘桌面端-索要与收取简历能力/) | `boss-resume-request-collection` | 请求简历、发送普通邀请、接收与下载附件、文件校验、哈希计算及 PDF/DOCX 解析 |

## 运行环境

- Windows 交互式桌面环境；锁屏或远程会话断开时，UI 自动化可能无法运行。
- 已安装并登录有权使用的 BOSS 直聘 Windows 桌面客户端。
- Python 与各 Skill 声明的依赖。候选人初评分 Skill 明确支持 Python 3.11–3.13。
- 当前自动化选择器主要按 BOSS 中文招聘端 `1.7.4.963` 验证。客户端更新后，应先验证 UIA 结构，不能用固定坐标或 OCR 绕过安全失败。

具体支持范围、初始化命令和安全边界以各目录中的 `SKILL.md` 为准。

## 安装

先克隆仓库：

```powershell
git clone https://github.com/9-dream-come-true-9/boss-zhipin-desktop-skills.git
Set-Location .\boss-zhipin-desktop-skills
```

然后把需要的 Skill 复制到所用智能体的 Skill 目录。不同智能体的目录位置和加载方式可能不同，请先查阅对应产品的扩展文档，并把下面的示例路径替换为实际目录。命令不会主动删除已有目录；如果目标同名目录已经存在，请先自行检查并决定如何处理。

```powershell
$skillsRoot = 'C:\path\to\your-agent\skills'
New-Item -ItemType Directory -Path $skillsRoot -Force | Out-Null

Copy-Item -LiteralPath '.\01-BOSS直聘桌面端-岗位发布' `
  -Destination (Join-Path $skillsRoot 'boss-job-publishing') -Recurse

Copy-Item -LiteralPath '.\02-BOSS直聘桌面端-候选人初评分' `
  -Destination (Join-Path $skillsRoot 'boss-candidate-scoring') -Recurse

Copy-Item -LiteralPath '.\03-BOSS直聘桌面端-候选人打招呼和消息交互' `
  -Destination (Join-Path $skillsRoot 'boss-candidate-messaging') -Recurse

Copy-Item -LiteralPath '.\04-BOSS直聘桌面端-索要与收取简历能力' `
  -Destination (Join-Path $skillsRoot 'boss-resume-request-collection') -Recurse
```

复制完成后，按照所用智能体的说明重新加载 Skill；部分智能体可能需要重启应用或刷新扩展目录。

## BOSS 直聘功能流程

### 岗位发布

1. `open_publish_form()` / `open-form`：进入并确认岗位发布表单已就绪，不填写字段、不点击最终发布。
2. `prepare_job_post()` / `prepare`：根据用户提供的实习岗位信息填写招聘类型、岗位名称、职位描述、学历、日薪、实习要求、账号地址和电话助手，并逐字段回读确认；本步骤不执行最终发布。
3. `get_run_status()` / `status`：查看本次岗位填写、字段核验、警告和提交状态。
4. `publish_reviewed_job()` / `publish-reviewed`：在全部字段核验一致后执行一次最终发布，并返回发布结果。
5. `reconcile_job_post()` / `reconcile`：当最终提交结果不确定时，只读核对是否发布成功，不重复点击发布。

该流程只支持实习生招聘；`prepare` 负责填写和核验，`publish-reviewed` 才会执行最终发布。

### 候选人初评分

1. `read_job_context()` / `job-context`：在 BOSS“职位 → 开放中”精确找到指定岗位，只读取得岗位名称、完整职位描述、学历和实习要求。
2. `score_query()` / `score-query`：只从该岗位的“消息”入口采集“新招呼”候选人，或按用户指定姓名查找唯一候选人，并输出有岗位证据支持的初步评分、档位和信息缺口。

未知信息不会被当成不匹配；该流程不发消息、不索要简历，也不下载简历。

### 候选人打招呼和消息交互

#### 打招呼

1. `open_surface()` / `open-surface`：打开 BOSS“推荐”页面，不执行后续候选人操作。
2. `select_job()` / `select-job`：在推荐页精确选择需要处理的岗位，并回读确认。
3. `list_candidate_cards()` / `list-candidates`：查看推荐页当前已加载的候选人及其可沟通状态。
4. `open_candidate_card()` / `open-candidate`：打开选定候选人；如果仍处于“打招呼”状态，会先触发平台默认招呼，再进入会话。
5. `greet_one()` / `greet-one`：在指定岗位下为一个可沟通候选人发送平台默认招呼，并继续发送用户提供的自定义消息。
6. `batch_greet()` / `batch-greet`：对指定岗位的一批可招呼候选人执行“平台默认招呼 + 自定义消息”。
7. `advance_list()` / `advance-list`：继续加载推荐候选人列表的下一段内容，不自动打开或发送。

当前版本的 `batch-greet --limit` 可能在消息已经发出后于汇总阶段报错，因此不得因为最终报错而自动重发。

#### 消息交互

1. `open_surface()` / `open-surface`：打开 BOSS“消息”页面，不执行后续会话操作。
2. `select_job()` / `select-job`：在消息页精确选择需要处理的岗位，并回读确认。
3. `list_message_rows()` / `list-conversations`：查看消息页当前已加载的候选人会话和消息预览。
4. `open_message_runtime()` / `open-conversation`：打开选定会话，并确认候选人、岗位和聊天窗口已经就绪。
5. `inspect_current_chat()` / `inspect-chat`：只读查看当前联系人、岗位和已加载的聊天消息。
6. `send_current()` / `send-current`：向当前已打开且核验一致的候选人会话发送一条自定义消息。
7. `advance_list()` / `advance-list`：继续加载消息会话列表的下一段内容，不自动打开或发送。
8. `open_next_unread()` / `open-next-unread`：打开指定岗位当前可处理的第一个未读候选人会话。
9. `open_conversation_exact()` / `open-conversation-exact`：根据岗位、联系人和完整最新消息打开并核验唯一会话。
10. `reply_current()` / `reply-current`：确认仍处于指定会话后发送本次回复。
11. `batch_message()` / `batch-message`：从指定岗位的消息列表顶部开始遍历现有会话，并向符合条件的候选人批量发送同一消息，同时避免重复发送。

所有自定义消息都会在发送前回读正文，并在发送后验证新消息。

### 索要与收取简历

#### 主动索要

1. `inspect_state()` / `inspect-state`：只读检查是否已向指定候选人发送平台简历请求、是否有待同意的附件请求，以及是否已经收到简历附件。
2. `request_platform()` / `request-platform`：点击 BOSS 平台“求简历”向指定候选人发起请求，并验证“简历请求已发送”；该方式可能消耗平台次数。

#### 主动发消息索要

1. `inspect_state()` / `inspect-state`：只读检查是否已向指定候选人发送平台简历请求、是否有待同意的附件请求，以及是否已经收到简历附件。
2. `request_message()` / `request-message`：向指定候选人发送普通简历邀请消息，不点击平台“求简历”，也不消耗平台求简历次数。
3. `accept_pending_attachment()` / `accept-pending`：候选人发起待处理的附件请求后，单次点击“同意”，并确认简历附件消息已经出现。

两种索要方式共用以下收取流程：

1. `download_received()` / `download-received`：将候选人已经发送的原始 PDF/DOCX 简历下载到用户指定目录，并确认下载文件有效。
2. `validate_file()` / `validate-file`：检查一个本地简历文件是否存在、非空，并且确实是与扩展名一致的 PDF 或 DOCX。
3. `parse_file()` / `parse-file`：校验并解析一个本地 PDF/DOCX 简历，返回解析是否成功及可读取内容规模。
4. `collect`：快捷执行“下载已收到的简历 → 校验原文件 → 解析”；没有附件时返回未收到，不会自动索要或自动同意附件。

`request-platform` 和 `request-message` 是二选一，不需要连续执行。用户只说“要简历”而未指定方式时，需要先选择其中一种。所有提交动作只执行一次；结果不确定时不会自动重试。

## 使用示例

安装后，可以通过自然语言描述任务，或在支持显式 Skill 调用的智能体中指定 Skill 标识符。下面以 `$skill-name` 形式展示调用示例；实际触发语法以所用智能体为准：

```text
$boss-job-publishing 根据我提供的完整岗位信息发布一个实习岗位。
```

```text
$boss-candidate-scoring 评估“产品运营实习生”岗位的新招呼候选人。
```

```text
$boss-candidate-messaging 查看“前端开发实习生”岗位的未读会话，并根据我提供的话术回复。
```

```text
$boss-resume-request-collection 检查指定候选人是否已经发送简历；如果已发送，下载并解析原始附件。
```

## 示例文件

### 岗位发布

- [BOSS直聘桌面端-文案策划｜岗位发布-输入模范.png](./examples/job-publishing/BOSS直聘桌面端-文案策划｜岗位发布-输入模范.png)
- [BOSS直聘桌面端-文案策划｜岗位发布.png](./examples/job-publishing/BOSS直聘桌面端-文案策划｜岗位发布.png)

### 候选人初评分

- [BOSS直聘桌面端-文案策划｜29名候选人初评分-姓名脱敏版.xlsx](./examples/candidate-scoring/BOSS直聘桌面端-文案策划｜29名候选人初评分-姓名脱敏版.xlsx)

### 候选人沟通

- [BOSS直聘桌面端-文案策划｜候选人打招呼和消息交互.png](./examples/candidate-messaging/BOSS直聘桌面端-文案策划｜候选人打招呼和消息交互.png)
- [BOSS直聘桌面端-文案策划｜候选人打招呼和消息交互2.png](./examples/candidate-messaging/BOSS直聘桌面端-文案策划｜候选人打招呼和消息交互2.png)

### 简历索要与收取

- [BOSS直聘桌面端-索要与收取简历能力.png](./examples/resume-collection/BOSS直聘桌面端-索要与收取简历能力.png)

### 四个 Skill 完整使用结果演示

- [文案策划｜候选人综合评估.png](./examples/full-workflow/文案策划｜候选人综合评估.png)

## 安全与隐私

- 提交运行示例前，应遮挡候选人姓名、联系方式等直接标识符，并确认自己有权公开剩余内容；本仓库示例中的候选人姓名已遮挡或替换为 `XXX`。
- 只在获得授权的招聘账号、岗位和候选人范围内使用这些 Skill。
- 发送消息、索要简历和发布岗位都会产生外部影响。运行前应理解对应 `SKILL.md` 中的提交边界、幂等控制与失败语义。
- 候选人评分只应作为有人工复核的初步辅助，不应替代最终招聘决定，也不应使用年龄、性别、婚育、照片、住址等与岗位无关或敏感的属性。
- 仓库中的 DOCX 是空白填写模板，不应在填写真实业务内容后重新提交到公开仓库。

## 版本

首个公开版本为 `v0.1.0`。

## 许可证

本仓库以 [Apache License 2.0](./LICENSE) 开源。第三方依赖、平台软件、产品名称和商标仍分别受其自身许可与权利约束。
