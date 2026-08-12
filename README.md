# BOSS 直聘 Windows 桌面端 Skill 合集

这是一组面向AI 智能体的 Windows 桌面自动化能力，通过 `pywinauto` 与 Windows UI Automation（UIA）操作 BOSS 直聘桌面客户端。

仓库包含四个彼此独立、可组合使用的 Skill。每个 Skill 都以自己的 `SKILL.md` 作为完整行为规范，并附带完成任务所需的脚本、Schema、模板或运行时资源。

> [!IMPORTANT]
> 本项目是非官方开源项目，与 BOSS 直聘及其运营主体不存在隶属、合作、赞助或认可关系。“BOSS 直聘”及相关名称、标识的权利归其权利人所有。使用者应自行确认其使用方式符合适用法律、组织政策和平台最新协议，并仅操作自己有权使用的账号与数据。

## 包含的 Skill

| Skill | 标识符 | 主要能力 |
| --- | --- | --- |
| [岗位发布](./01-BOSS直聘桌面端-岗位发布/) | `boss-job-publishing` | 填写、回读核验并真实发布实习生招聘、社招全职、应届校园招聘和兼职招聘岗位 |
| [候选人初评分](./02-BOSS直聘桌面端-候选人初评分/) | `boss-candidate-scoring` | 读取指定岗位要求，仅从“消息”入口采集候选人，并进行有证据边界的初步评分 |
| [候选人打招呼和消息交互](./03-BOSS直聘桌面端-候选人打招呼和消息交互/) | `boss-candidate-messaging` | 根据上传文档回复消息、在消息页批量发信息、在推荐页批量打招呼，以及给指定联系人发信息 |
| [索要与收取简历](./04-BOSS直聘桌面端-索要与收取简历能力/) | `boss-resume-request-collection` | 通过平台主动索要或普通消息索要简历、同意待处理附件请求，并下载候选人已发送的原始简历 |

## 运行环境

- Windows 交互式桌面环境；锁屏或远程会话断开时，UI 自动化可能无法运行。
- 已安装并登录有权使用的 BOSS 直聘 Windows 桌面客户端。
- Python 与各 Skill 声明的依赖。候选人初评分 Skill 明确支持 Python 3.11–3.13。
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

该 Skill 可以在 BOSS 直聘桌面端完成以下四类岗位发布：

#### 实习生招聘

根据岗位信息填写职位名称、职位描述、学历、日薪、实习月数、每周到岗天数、账号已有地址和电话交换助手，并执行岗位的真实发布
#### 社招全职

根据岗位信息填写职位名称、职位描述、经验、学历、月薪、账号已有地址和电话交换助手，并执行岗位的真实发布

#### 应届校园招聘

根据岗位信息填写职位名称、职位描述、固定“在校/应届”经验、学历、月薪、毕业时间、账号已有地址和电话交换助手，并执行岗位的真实发布

#### 兼职招聘

根据岗位信息填写职位名称、职位描述、经验、学历、结算方式、薪资单位及区间、兼职周期、工作时段、每周天数、班次、招聘截止日期、账号已有地址和电话交换助手，并执行岗位的真实发布

### 候选人初评分

从该岗位的“消息”入口采集“新招呼”候选人，或按用户指定姓名查找唯一候选人，并输出有岗位证据支持的初步评分、档位和信息缺口。

### 候选人打招呼和消息交互

#### 打招呼

1. 在 BOSS“推荐”页精确选择岗位，向尚未沟通的候选人批量发送“平台默认招呼 + 自定义消息”；可通过 `--limit` 处理 1–50 人，或通过 `--all` 处理当前可发现对象并受 200 人安全上限约束。

#### 消息交互

1. 根据用户本次上传的问题规则 DOCX 和回答依据 DOCX，向候选人回复信息
3. 按联系人完整姓名进行精确搜索，回读会话标题一致后发送一条信息。
4. 在 BOSS“消息”页的精确岗位下，向已有会话批量发送同一条信息；支持限定数量或处理全部可发现会话


### 索要与收取简历

#### 主动索要

1.点击 BOSS 平台“求简历”向指定候选人发起请求，并验证“简历请求已发送”；该方式可能消耗平台次数。

#### 主动发消息索要

2.向指定候选人发送普通简历邀请消息，不点击平台“求简历”，也不消耗平台求简历次数。

#### 收取简历

1. 当候选人发起待处理的附件请求时，单次点击“同意”并验证简历附件消息出现；平台主动索要和普通消息索要后都可能需要单独执行该能力。
2.将候选人已经发送的原始 PDF/DOCX 简历下载到用户指定目录，并校验下载文件。


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

