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

## Skill 功能与函数

下面列出当前脚本实际提供的主要业务函数和 CLI 子命令。哈希计算、文本规范化、JSON 包装和底层控件查找等内部辅助函数不单独展开；完整参数、返回值、安全失败语义和操作边界以各 Skill 的 `SKILL.md` 为准。

### 岗位发布

主要脚本：[boss_jobs.py](./01-BOSS直聘桌面端-岗位发布/scripts/boss_jobs.py) 与 [ensure_runtime.py](./01-BOSS直聘桌面端-岗位发布/scripts/ensure_runtime.py)

| `BossJobs` 业务函数 / CLI | 功能 |
| --- | --- |
| `ensure_runtime.py` | 校验 Python 3.11–3.13、依赖和内置 wheel SHA-256，并按需安装或重新安装固定运行包后在新进程中复验来源。 |
| `runtime` | 返回 Python 可执行文件，并校验运行包版本、发行版版本、build ID 和 selector profile，同时报告模块来源。 |
| `inspect_environment()` / `inspect` | 只读检查客户端安装、进程、窗口、版本和 UIA 语义可访问性。 |
| `open_publish_form()` / `open-form` | 进入并确认岗位发布表单已就绪，不填写字段、不点击最终发布。 |
| `prepare_job_post()` / `prepare` | 校验实习岗位 JSON，填写招聘类型、名称、描述、学历、日薪、实习月份、到岗天数、账号地址和电话助手，并逐字段回读生成 `REVIEW_READY` 记录。 |
| `get_run_status()` / `status` | 只读查询运行状态、公司、逐字段证据、警告、提交时间和诊断目录。 |
| `authorize_job_post()` | 仅为处于 `REVIEW_READY` 的运行签发短时内部授权令牌；令牌不作为 CLI 参数暴露。 |
| `publish_prepared_job()` | 校验短时令牌、公司上下文和逐字段证据，再跨越一次性最终提交边界。 |
| `publish_reviewed_job()` / `publish-reviewed` | 组合内部授权与最终发布；只有全部字段验证通过时才调用一次精确“发布”按钮。 |
| `reconcile_job_post()` / `reconcile` | 对 `SUBMITTING` 或 `COMMIT_UNKNOWN` 运行做只读结果核对，不再次点击发布。 |

该 Skill 只支持“实习生招聘”。工作地址只使用账号已有地址；不操作职位类型和职位关键词。`open-form` 可选 `--timeout`、`--artifact-dir` 与 `--no-maximize`；`prepare` 要求 `--spec-file` 和稳定的 `--idempotency-key`，并支持相同的可选参数；`status`、`publish-reviewed` 与 `reconcile` 都要求 `--run-id`。同一次岗位发布意图必须复用同一 `idempotency_key`，同一键不能绑定不同岗位内容。`prepare` 只填写并回读，`publish-reviewed` 才会产生最终外部提交；已成功或进入 `SUBMITTING` / `COMMIT_UNKNOWN` 的运行不得重新准备或再次发布，结果不确定时只能调用 `reconcile`。

### 候选人初评分

主要脚本：[boss_candidate_scoring.py](./02-BOSS直聘桌面端-候选人初评分/scripts/boss_candidate_scoring.py)、[boss_scoring_runtime.py](./02-BOSS直聘桌面端-候选人初评分/scripts/boss_scoring_runtime.py) 与 [ensure_runtime.py](./02-BOSS直聘桌面端-候选人初评分/scripts/ensure_runtime.py)

| 主要函数 / CLI | 功能 |
| --- | --- |
| `ensure_runtime.py` | 校验 Windows 与 Python 版本、必需依赖和内置 wheel SHA-256，并按需安装和复验固定运行包；支持 `--dry-run` 与 `--force`。 |
| `runtime()` / `runtime` | 校验运行包版本、发行版版本、build ID 和 selector profile，并报告 Python 解释器与模块来源。 |
| `read_job_context()` / `job-context` | 在“职位 → 开放中”精确定位唯一岗位，只读回读职位名称、完整描述、学历和实习要求，生成可复用的岗位上下文与 `source_hash`。 |
| `normalize_requirements()`、`build_rubric()` | 校验从 JD 提取的要求、原文位置、字段白名单与条件类型，过滤敏感条件，并生成固定 hard gate、权重、阈值和规则版本。 |
| `collect_message_candidates()` | 仅从“消息”入口采集候选人；批量模式使用“新招呼”，单人模式在该岗位固定消息队列中按显示名精确查找。 |
| `candidate_information()` | 将安全可见资料按教育、经历、项目、技能、到岗、求职方向和其他事实分类，并保留原始来源文本。 |
| `evaluate_criterion()` | 对单条岗位要求生成 `MATCH`、`PARTIAL`、`MISMATCH` 或 `UNKNOWN` 结论，并附带候选人事实、来源文本、权重和置信度。 |
| `score_candidate()` | 对一个不可变候选人快照计算 hard gate、已知证据得分、覆盖率、档位、理由代码、信息缺口、冲突和计算公式。 |
| `score_query()` / `score-query` | 复用岗位上下文，校验 requirements 与 JD 哈希，采集单人或批量候选人，逐人评分并汇总可解释结果；默认人数上限为 `50`。 |
| `inspect` | 只读返回运行时来源和 BOSS 客户端环境诊断，不采集或评分候选人。 |

评分时，未知信息不作为不匹配，也不进入得分分母；证据覆盖率单独计算。`job-context` 使用 `--job-query`；`score-query` 使用 `--job-query`、`--requirements-file`、`--job-context-file`，并可选 `--candidate-query` 与 `--limit`。`--limit` 默认为 `50`，有效范围为 `1–200`。该 Skill 不发消息、不求简历、不下载简历，也不访问推荐、互动或人才搜索。

### 候选人打招呼和消息交互

主要脚本：[boss_messages.py](./03-BOSS直聘桌面端-候选人打招呼和消息交互/scripts/boss_messages.py)

| 主要函数 / CLI | 功能 |
| --- | --- |
| `window()` / `inspect` | 只读检查唯一、可访问的 BOSS 主窗口和 UIA 节点。 |
| `doc_text()` / `parse-docs` | 读取问题与回答 DOCX 的非空段落，输出当次问题消息和回答依据，不把业务内容写入 Skill。 |
| `open_surface()` / `open-surface` | 只打开“推荐”或“消息”页面，不选择岗位、不读取列表、不发送。 |
| `select_job()` / `select-job` | 在推荐页或消息页精确选择岗位并回读确认；同名分类无法唯一消歧时安全停止。 |
| `list_candidate_cards()` / `list-candidates` | 只读返回推荐页当前真实可见候选人卡片的 RuntimeId、状态和文本。 |
| `open_candidate_card()` / `open-candidate` | 按当前可见 RuntimeId 打开一个候选人卡片；若卡片仍为“打招呼”状态，会触发一次平台默认招呼并进入“继续沟通”，但不输入自定义文本。 |
| `list_message_rows()` / `list-conversations` | 只读返回消息页当前真实可见会话行的 RuntimeId 和预览文本。 |
| `open_message_runtime()` / `open-conversation` | 按当前可见 RuntimeId 打开会话，等待编辑器就绪，并可校验预期岗位。 |
| `inspect_current_chat()` / `inspect-chat` | 只读返回当前联系人、岗位候选、已加载的 `mid-*` 消息容器和编辑器 ID。 |
| `advance_list()` / `advance-list` | 通过真实滚轮和重叠视口验证推进推荐列表或消息列表，不打开条目、不发送消息。 |
| `send_current()`、`semantic_write_and_send()` / `send-current` | 校验可选联系人与岗位，清空草稿，输入并全文回读，单次提交后验证编辑器清空和唯一新消息容器。 |
| `greet_one()` / `greet-one` | 在指定推荐岗位下先触发一次平台默认招呼，再进入会话发送调用方提供的一条自定义消息。 |
| `batch_greet()` / `batch-greet` | 批量处理推荐页可招呼候选人，对每人执行“平台默认招呼 + 自定义消息”；支持 `--limit` 或 `--all`，自定义消息提交状态未知时停止整批且不重发。 |
| `batch_message()` / `batch-message` | 从消息列表顶部开始按重叠视口遍历现有会话，逐条校验联系人和岗位，并使用“岗位主体 + 联系人 + 消息摘要”持久账本跨批次防重。 |
| `open_next_unread()` / `open-next-unread` | 打开指定岗位当前可见的第一个未读会话，并返回会话与最新候选人消息。 |
| `open_conversation_exact()` / `open-conversation-exact` | 先精确选择岗位，再以完整最新消息在当前可见列表中确定唯一会话；打开后核验联系人标题和岗位。 |
| `reply_current()` / `reply-current` | 确认当前编辑器仍属于指定会话后发送回复，并执行与当前会话发送相同的提交验证。 |

RuntimeId 只在当前 UIA 会话和当前可见视口内有效。所有自定义文本发送都会执行正文回读和新消息容器验证；平台默认招呼通过卡片从“打招呼”变为“继续沟通”来推进，不适用自定义正文回读验证。`batch-greet --limit` 的有效范围为 `1–50`，`--all` 的安全上限为 `200`；`batch-message --limit` 的有效范围为 `1–100`，`--all` 的安全上限为 `500`。`batch-message` 的持久账本位于 Skill 目录外，不保存消息正文，账本命中的跳过项不计入实际发送数量。`parse-docs` 要求两份 DOCX 各至少有两个非空段落，并把第一段作为模板标题跳过。

当前版本的 `batch-greet --limit` 在成功完成目标数量后的汇总阶段会因未定义计数变量报错。报错可能发生在外部发送已经完成之后，且最终错误响应不包含逐条结果，因此不得据此自动重跑；修复前应优先使用原子命令逐条编排。

### 索要与收取简历

主要脚本：[boss_resume.py](./04-BOSS直聘桌面端-索要与收取简历能力/scripts/boss_resume.py)

| Skill 能力 / 主要函数 / CLI | 功能 |
| --- | --- |
| `runtime` | 返回当前 Python 与 `pywinauto` 运行时信息。 |
| `inspect_resume_state`、`inspect_state()` / `inspect-state` | 只读检查是否已发起平台简历请求、是否存在待同意附件请求，以及是否已有附件消息。 |
| `request_resume_by_platform`、`request_platform()` / `request-platform` | 点击平台“求简历”，确认唯一授权弹窗，并验证新增“简历请求已发送”消息；该方式可能消耗平台次数。 |
| `request_resume_by_message`、`request_message()` / `request-message` | 发送普通邀请消息；不点击“求简历”，不消耗平台次数，支持外部 UTF-8 消息文件。 |
| `accept_pending_resume_attachment`、`accept_pending_attachment()` / `accept-pending` | 对唯一待处理附件请求点击一次“同意”，并以新增附件消息作为成功证据。 |
| `download_received_resume`、`download_received()` / `download-received` | 下载候选人已经发送的原始 PDF/DOCX 到指定目录，并立即执行格式、大小和 SHA-256 校验。 |
| `validate_resume_file`、`validate_file()` / `validate-file` | 校验文件存在性、大小、扩展名、真实文件签名和 SHA-256，不解析正文。 |
| `parse_resume_file`、`parse_file()` / `parse-file` | 校验后解析 PDF 或 DOCX，返回解析状态与文本长度，不修改原件或执行宏。 |
| `collect_received_resume` / `collect` | 当前 CLI 实际组合“下载 → 校验 → 解析”；没有附件时返回 `NOT_RECEIVED`，不会自动索要或自动同意待处理附件。 |

平台请求、普通消息和同意附件都只提交一次，并在新增消息容器中验证结果；进入 `COMMIT_UNKNOWN` 后禁止自动重试。存在多个待处理请求或附件时，必须使用消息 ID 精确选择。Skill 规范描述了批量请求能力和 `BatchReceipt`，但当前脚本没有独立批量函数或 CLI；批量任务需要调用方逐个编排上述原子命令。

主要 CLI 参数：状态检查使用 `--job` 与 `--candidate`；两种请求还要求稳定的 `--request-id`，普通消息可选 `--message-file`；同意附件可选 `--request-message-id`；下载和 `collect` 要求 `--output-dir`，并可选 `--attachment-message-id`；文件校验与解析使用 `--file`。平台请求和普通消息以岗位、候选人、请求模式及 `request_id` 形成持久账本键；命中已有请求或历史成功证据时不再执行外部操作。

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

- [文案策划｜候选人综合评估.png](./examples/candidate-scoring/文案策划｜候选人综合评估.png)

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
