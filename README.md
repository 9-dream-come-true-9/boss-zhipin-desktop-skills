# BOSS 直聘 Windows 桌面端 Skill 合集

这是一组面向支持本地 Skill 或工具扩展机制的 AI 智能体的 Windows 桌面自动化能力，通过 `pywinauto` 与 Windows UI Automation（UIA）操作 BOSS 直聘桌面客户端。

仓库包含四个彼此独立、可组合使用的 Skill。每个 Skill 都以自己的 `SKILL.md` 作为完整行为规范，并附带完成任务所需的脚本、Schema、模板或运行时资源。

> [!IMPORTANT]
> 本项目是非官方开源项目，与 BOSS 直聘及其运营主体不存在隶属、合作、赞助或认可关系。“BOSS 直聘”及相关名称、标识的权利归其权利人所有。使用者应自行确认其使用方式符合适用法律、组织政策和平台最新协议，并仅操作自己有权使用的账号与数据。

## 包含的 Skill

| Skill | 标识符 | 主要能力 |
| --- | --- | --- |
| [岗位发布](./01-BOSS直聘桌面端-岗位发布/) | `boss-job-publishing` | 填写、回读核验并发布实习生招聘、社招全职、应届校园招聘和兼职招聘岗位，以及核对结果不确定的提交 |
| [候选人初评分](./02-BOSS直聘桌面端-候选人初评分/) | `boss-candidate-scoring` | 读取指定岗位要求，仅从“消息”入口采集候选人，并进行有证据边界的初步评分 |
| [候选人打招呼和消息交互](./03-BOSS直聘桌面端-候选人打招呼和消息交互/) | `boss-candidate-messaging` | 根据上传文档回复消息、在消息页批量发信息、在推荐页批量打招呼，以及给指定联系人发信息 |
| [索要与收取简历](./04-BOSS直聘桌面端-索要与收取简历能力/) | `boss-resume-request-collection` | 通过平台主动索要或普通消息索要简历、同意待处理附件请求，并下载候选人已发送的原始简历 |

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
2. `prepare_job_post()` / `prepare`：根据 `recruitment_type` 填写四类岗位共用字段及对应的专属字段，并逐字段回读确认；本步骤不执行最终发布。
3. `get_run_status()` / `status`：查看本次岗位填写、字段核验、警告和提交状态。
4. `publish_reviewed_job()` / `publish-reviewed`：在全部字段核验一致后执行一次最终发布，并返回发布结果。
5. `reconcile_job_post()` / `reconcile`：当最终提交结果不确定时，只读核对是否发布成功，不重复点击发布。

四类岗位的专属字段如下：

- 实习生招聘：学历、日薪、实习月数和每周到岗天数。
- 社招全职：经验、学历和月薪。
- 应届校园招聘：固定“在校/应届”经验、学历、月薪和毕业时间。
- 兼职招聘：经验、学历、结算方式、薪资单位及区间、兼职周期、工作时段、每周天数、班次和招聘截止日期。

四种招聘类型共用“进入表单 → 填写并回读 → 查看状态 → 单次发布 → 结果不确定时只读核对”的安全流程；`prepare` 负责填写和核验，`publish-reviewed` 才执行最终发布。

### 候选人初评分

1. `read_job_context()` / `job-context`：在 BOSS“职位 → 开放中”精确找到指定岗位，只读取得岗位名称、完整职位描述、学历和实习要求。
2. `score_query()` / `score-query`：只从该岗位的“消息”入口采集“新招呼”候选人，或按用户指定姓名查找唯一候选人，并输出有岗位证据支持的初步评分、档位和信息缺口。

未知信息不会被当成不匹配；该流程不发消息、不索要简历，也不下载简历。

### 候选人打招呼和消息交互

#### 打招呼

1. `batch_greet()` / `batch-greet`：在 BOSS“推荐”页精确选择岗位，向尚未沟通的候选人批量发送“平台默认招呼 + 自定义消息”；可通过 `--limit` 处理 1–50 人，或通过 `--all` 处理当前可发现对象并受 200 人安全上限约束。

#### 消息交互

1. `parse-docs`：解析用户本次上传的问题规则 DOCX 和回答依据 DOCX；文档缺失或仍为空白模板时停止，不继续回复。
2. `open_next_unread()` / `open-next-unread`：打开指定岗位的下一条未读会话，返回本次会话标识和候选人的最新消息。
3. `reply_current()` / `reply-current`：确认当前会话没有切换后，发送根据上传文档生成的有依据回复；文档没有依据或内容冲突时转人工处理，不发送。
4. `batch_message()` / `batch-message`：在 BOSS“消息”页的精确岗位下，向已有会话批量发送同一条信息；支持限定数量或处理全部可发现会话，并通过持久化账本避免重复发送。
5. `send_message_to_contact()` / `send-to-contact`：按联系人完整姓名进行精确搜索，回读会话标题一致后发送一条信息。

前三项组成“根据上传文档回复消息”的完整流程。所有消息都会在发送前核验对象和正文，并在发送后验证新消息；发送结果不确定时不会自动重发。

### 索要与收取简历

#### 主动索要

1. `request_platform()` / `request-platform`：点击 BOSS 平台“求简历”向指定候选人发起请求，并验证“简历请求已发送”；该方式可能消耗平台次数。

#### 主动发消息索要

1. `request_message()` / `request-message`：向指定候选人发送普通简历邀请消息，不点击平台“求简历”，也不消耗平台求简历次数。

#### 收取简历

1. `accept_pending_attachment()` / `accept-pending`：当候选人发起待处理的附件请求时，单次点击“同意”并验证简历附件消息出现；平台主动索要和普通消息索要后都可能需要单独执行该能力。
2. `download_received()` / `download-received`：将候选人已经发送的原始 PDF/DOCX 简历下载到用户指定目录，并校验下载文件。

以上四项是彼此独立的业务能力，不是固定的必经链路。`request-platform` 和 `request-message` 是二选一；用户只说“要简历”而未指定方式时，需要先选择其中一种。只读状态检查、文件校验和解析由智能体按任务需要作为内部辅助调用。所有提交动作只执行一次；结果不确定时不会自动重试。

## 使用示例

安装后，可以通过自然语言描述任务，或在支持显式 Skill 调用的智能体中指定 Skill 标识符。下面以 `$skill-name` 形式展示调用示例；实际触发语法以所用智能体为准：

```text
$boss-job-publishing 根据我提供的完整岗位信息发布一个岗位，招聘类型为社招全职。
```

```text
$boss-candidate-scoring 评估“产品运营实习生”岗位的新招呼候选人。
```

```text
$boss-candidate-messaging 根据我上传的问答文档，处理“前端开发实习生”岗位的下一条未读会话，并回复有直接依据的问题。
```

```text
$boss-resume-request-collection 使用普通消息向指定候选人索要简历，不消耗平台求简历次数。
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
