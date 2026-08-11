---
name: boss-candidate-scoring
description: 打开 BOSS 直聘 Windows 桌面客户端，定位指定的已发布岗位及其职位描述，仅从“消息”入口采集具名候选人，并依据从职位描述中提取的标准进行有证据边界的初步评分。适用于用户询问指定 BOSS 岗位中哪些候选人更有潜力，或要求评估指定候选人的场景。不要向用户索要评分规则、候选人快照或内容哈希。
---

# BOSS 候选人初步评分

通过 `scripts/boss_candidate_scoring.py` 调用固定 pywinauto 函数完成“读取岗位要求 → 从消息采集候选人 → 单人评分”。用户只需说明要查询的岗位，以及可选的候选人姓名；不得把评分标准、候选人 JSON 或哈希改成用户输入。

## 固定边界

- 候选人入口只有 BOSS 左侧“消息”。未指定姓名时固定使用“消息 → 顶部岗位筛选 → 新招呼”；指定姓名时只在该岗位的消息固定队列中做精确姓名查询，不访问推荐、互动、人才搜索或意向沟通。
- 允许打开 BOSS：若客户端未运行，函数启动已安装的官方客户端；若未登录则返回 `LOGIN_REQUIRED`，不自动登录、扫码或填写验证码。
- 不关闭或重启 BOSS，不使用 `restart_for_accessibility=True`，避免破坏登录状态。
- 岗位与候选人都通过 UIA 名称、控件类型、作用域和回读证据定位；不使用 OCR、截图识别、绝对坐标或列表序号。
- 不执行候选人去重、合并或账本更新。每条消息会话独立采集、独立评分；同名会话不得猜测为同一个人。
- 不发招呼、回复或求简历，不下载简历，不生成 P4 最终候选人名单。
- 姓名只用于定位和展示，绝不进入评分规则、分数或档位。
- 不把任何一次真实 JD、候选人资料或评分结果写入 Skill 目录。

## 跨电脑运行边界

- Skill 不依赖用户名、固定盘符、窗口坐标、分辨率、原电脑候选人账本或原电脑发布记录。没有本地发布记录时，直接从当前账号的 BOSS 职位编辑页只读取得 JD。
- 支持 Windows 交互式桌面、Python 3.11–3.13，以及已验证的 BOSS 中文招聘端 `1.7.4.963`。其他客户端版本必须先制作并验证对应 selector profile；当前版本遇到未知/不匹配版本时返回 `UNSUPPORTED_VERSION`，不得绕过。
- 客户端路径按“当前用户运行进程 → `BOSS_ZHIPIN_EXE` → `LOCALAPPDATA`/`PROGRAMFILES` 等系统环境目录 → Windows 卸载注册表”自动发现，不写死 `C:\Users\...` 或 `C:`。自定义安装无法自动发现时，只需把 `BOSS_ZHIPIN_EXE` 指向真实的 `boss-zhipin.exe`。
- 主窗口按当前用户 BOSS 进程 PID 绑定；标题仅用于在多个同进程窗口中确认主窗，不要求窗口标题完全等于“BOSS直聘”。慢电脑启动时等待唯一主窗口，而不是只等待后台进程。
- pywinauto、pywin32、psutil、comtypes 等固定版本依赖直接安装到执行 `python` 所对应的全局环境；需要安装或版本不一致时调用 `pip --upgrade --force-reinstall`。首次安装需要联网；执行前后都校验主 wheel SHA-256、版本、build ID、selector profile 和真实模块路径。
- 机器锁屏、远程会话断开、BOSS 未登录或账号灰度 UI 与已验证语义结构不一致时安全停止，不进行坐标兜底。

## 用户输入

从用户请求中提取：

- `job_query`：岗位名称，必须与 BOSS 开放职位的名称精确一致。
- `candidate_query`：可选；用户指定姓名时只保留显示名精确一致的消息会话。
- `limit`：可选，默认 50。

用户已经说明岗位时直接运行。只有完全没有岗位查询范围时，才询问“要评估哪个岗位”；不得询问评分标准、候选人快照、`candidate_key`、`job_key` 或 `content_hash`。

## 初始化

每个新任务在第一次 UI 操作前运行：

```powershell
python "<skill_dir>\scripts\ensure_runtime.py"
python "<skill_dir>\scripts\boss_candidate_scoring.py" runtime
```

两条命令必须成功，且 runtime provenance 与 Skill 内固定的版本、build ID、selector profile 完全一致。每个命令使用新的 Python 进程；不要在已导入旧 runtime 的解释器中重试。

失败时才执行只读诊断：

```powershell
python "<skill_dir>\scripts\boss_candidate_scoring.py" inspect
```

## 读取岗位描述

调用固定函数，并把完整输出保存到 Skill 目录之外的任务文件。**采集岗位 JD 时，必须由 Python 直接以 UTF-8 写入 `job-context.json`，禁止经过 PowerShell 的 `>`、`Out-File`、`Set-Content` 或其他文本管道，避免中文编码损坏。**

```python
import subprocess
import sys
from pathlib import Path

skill_dir = Path("<skill_dir>")
task_dir = Path("<task_dir>")
proc = subprocess.run(
    [
        sys.executable,
        str(skill_dir / "scripts" / "boss_candidate_scoring.py"),
        "job-context",
        "--job-query",
        "<精确岗位名称>",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="strict",
    check=False,
)
(task_dir / "job-context.json").write_text(proc.stdout, encoding="utf-8")
(task_dir / "job-context.stderr.txt").write_text(proc.stderr, encoding="utf-8")
if proc.returncode != 0:
    raise SystemExit(proc.returncode)
```

岗位 JD 的唯一来源是当前账号 BOSS“职位 → 开放中”：定位唯一精确标题的职位卡，只读打开该卡内唯一“编辑”，通过 ValuePattern 回读职位名称、完整职位描述、学历与实习要求；不点击“保存并发布”。不得读取或优先采用本机发布记录。

`job-context.json` 是本次任务已核验的岗位上下文。后续同一任务内首次执行、失败重试或候选人续采，都必须复用该文件；不得再次进入“职位”读取 JD。只有以下情况才重新执行 `job-context`：用户开始了新的独立任务、缓存文件不存在、缓存完整性校验失败，或用户明确要求刷新 JD。

输出中的 `source_hash` 只覆盖职位名称、职位描述、学历和实习要求。薪资、地址、电话、年龄、性别、婚育等信息不得形成评分条件。

## Agent 从 JD 提取要求

Agent 直接阅读 `job-context` 返回的职位描述和结构化要求，生成当次临时 `requirements.json`。该文件必须位于 Skill 目录之外，并符合 `references/requirements.schema.json`。

每条要求只包含：

- `source_pointer`：来源字段，如 `/education`、`/internship/days_per_week` 或 `/description`。
- `source_span`：JD 中支持该要求的原文；结构化字段使用其规范文本。
- `field`：`education`、`major`、`availability`、`desired_role`、`experience_summary` 或 `skills`。
- `canonical_value`：用于比较的规范要求；数值要求使用 `{"value": 3, "unit": "months"}` 或 `{"value": 3, "unit": "days_per_week"}`。
- `value_type`：`education_at_least`、`number_at_least`、`positive_term_any` 或 `positive_term_all`。
- `modality`：`required`、`core` 或 `preferred`，必须忠实反映“必须/核心条件”、普通任职要求与“优先/加分”等原文。

不要让 Agent 自定 gate、权重、阈值或排除词；固定脚本根据 `value_type` 与 `modality` 生成。结构化学历和实习时长由函数自动加入，不必重复提取。职责、福利、公司宣传、薪资，以及受保护/敏感属性不进入要求。信息不明确时跳过该条，不能猜测。

## 固定采集并评分

调用一个高层固定函数：

```powershell
python "<skill_dir>\scripts\boss_candidate_scoring.py" score-query `
  --job-query "<精确岗位名称>" `
  --requirements-file "<temporary-requirements.json>" `
  --job-context-file "<task_dir>\job-context.json" `
  --limit 50
```

用户指定姓名时增加：

```powershell
  --candidate-query "<候选人显示名>"
```

`score-query` 内部固定执行：

1. 从 `--job-context-file` 恢复本次任务已经核验的唯一开放岗位和 JD；验证缓存自身完整性及 `requirements.json.source_hash` 一致性，但不再次打开“职位”或岗位编辑页。
2. 进入“消息”，展开消息列表上方的岗位筛选框；只选择文本形如 `岗位名 _ 城市 薪资`、标题与目标岗位精确一致且父控件为 `ListItem` 的唯一项。选择后必须从同一顶部筛选控件回读当前岗位；不通过消息正文中的岗位名判断筛选状态，也不扫描其他入口。
3. 未指定姓名时打开“新招呼”并从消息行采集 `candidate_ref.display_name`；指定姓名时依次在“新招呼、未读、沟通中、已约面、全部”等消息固定队列中查找显示名与岗位都精确命中的唯一会话，不调用人才搜索。
4. 打开该消息会话并读取当前资料，统一生成 `messages.current_profile` 单人快照。
5. 在函数内部重新计算并核对快照 `content_hash`；哈希是内部完整性证据，不要求用户提供。
6. 对每个快照分别调用 `score_candidate()`，不合并、不去重。

内部 JSON 必须保留每人的 `candidate_name`、`candidate_key`、分数、证据覆盖率、档位、命中证据、信息缺口与原始 `content_hash`，用于一致性校验。面向用户的结果默认不展示 `candidate_key` 或哈希，也不得输出性别、年龄、照片、联系方式、住址等非必要个人信息。

## 消息列表完整遍历（v3-pywinauto-wheel）

未指定候选人姓名的批量采集不能依赖 `Document.TextRange` 中的“滚动加载更多”。BOSS 1.7.4.963 的消息列表是虚拟列表：UIA 会保留大量屏外 `ListItem`，但其矩形为 `(0,0,0,0)`；Document 也不对该列表暴露可用的 `ScrollPattern`。因此固定使用 pywinauto 真实鼠标滚轮，并遵守以下协议：

1. 进入“消息 → 精确岗位 → 新招呼”后，只保留矩形有效且与 BOSS 主窗口相交的候选人消息行；不能把屏外零矩形行当成已处理。
2. 用当前可见候选人行矩形的交集中心作为滚轮落点，不使用固定屏幕坐标，也不在聊天区滚动。
3. 先以向上滚轮归一到列表顶部；连续两次滚动后可见行签名不变，才确认顶部边界。
4. 从顶部开始向下遍历。每次滚动 5 个 wheel notch，小于一个完整视口，确保相邻视口至少保留重叠行用于漏项校验。
5. 同一 UIA 会话内使用 `runtime_id + 行文本` 形成行身份；打开详情后再用唯一姓名、当前岗位和 `mid-*` 会话锚点确认候选人身份。不得仅按姓名合并。
6. 每个视口先处理所有尚未处理的可见行，再继续向下。达到 `limit` 后停止；连续无变化才判定底部边界。
7. 遍历不设置固定总秒数。仍保留向上最多 40 轮、向下最多 80 轮，以及连续无变化的边界判定；达到轮次上限时返回 `CANDIDATE_SEARCH_LIMIT_REACHED`，禁止无限滚动。外层执行器必须允许该有界遍历自然完成，不得设置短于实际任务的固定超时。

“全部”分类只用于滚动机制的覆盖测试，因为候选人数量充足；正式批量评分仍保持固定业务边界“新招呼”。已在“全部”分类验证：首屏 8 行，通过 4 个重叠向下视口可发现 35 个唯一消息行，前 3 个视口已超过 20 行。


## 评分语义

- 未知信息始终是 `UNKNOWN`，不能因为资料没写就判定不匹配。
- `score` 只在已知的加权条件上计算；未知项不进入得分分母。
- `coverage` 单独表示已知加权证据占全部加权要求的比例。
- 没有已知加权项时 `score=null`；覆盖率不足时档位是 `INSUFFICIENT_EVIDENCE`。
- 只有岗位明确要求的 hard gate 出现明确反例，才能标记 `NOT_RECOMMENDED`。
- 学历和实习时长使用有序/数值比较；任意技能或经验要求不能用“没有命中关键词”推断为不具备。

## 安全失败

- `APP_NOT_RUNNING`：固定启动官方 BOSS 后等待窗口；只重试一次。
- `LOGIN_REQUIRED`：停止并请用户完成登录；不做身份验证自动化。
- `UNSUPPORTED_VERSION`：客户端版本未知或不是已验证版本；不得放宽版本门，应更新并实测 selector profile。
- `AMBIGUOUS_JOB`：报告精确标题匹配数量，不按列表位置猜选。
- `JOB_SOURCE_UNAVAILABLE`：岗位发布记录和 BOSS 职位详情都不可用；不索要外部 rubric。
- `CANDIDATE_NOT_FOUND`：未指定姓名时，当前岗位消息的新招呼中没有候选人；指定姓名时，该岗位的消息固定队列中没有唯一精确命中。
- `CANDIDATE_IDENTITY_CONFLICT`：同一动作范围无法锁定唯一消息会话时停止，不按姓名合并。
- `STALE_JOB_SOURCE`：JD 已变化，重新执行 `job-context` 并由 Agent 从新 JD 生成 requirements。
- `STALE_OR_TAMPERED_SNAPSHOT`：重新采集该消息会话；不得继续使用旧快照。
- `UNSAFE_SCORING_CRITERION`：删除受保护或与岗位无关条件，不放宽白名单。

完成后只向用户报告带姓名的评估结果和必要证据；不要暴露内部 JSON、哈希或 runtime 路径，除非用户明确要求诊断。


## 修复说明（0.4.3）

修复 BOSS 1.7.4.963 在部分账号/UI 灰度下将岗位编辑表单重复暴露为嵌套 UIA Document 时，旧版因要求 Document 数量严格等于 1 而错误返回 `ACCESSIBILITY_UNAVAILABLE` 的问题。新版在多个语义完整的 Document 中选择面积最小的可见内容作用域；若最优候选仍无法唯一消歧则继续安全失败。

## 修复说明（0.4.3-local-single-session）

修复 `score-query` 在已经读取并校验岗位描述后，采集每位候选人详情时反复导航到“职位”、重复选择岗位并重新读取职位详情的问题。

根因：旧流程先 `scan_new_greetings()` 获取列表，再对每位候选人逐个调用 `read_message_candidate_profile()`；后者每次都会新建 UIA 连接，并执行“消息 → 选择岗位 → 队列 → 查找会话”，造成重复点击。Electron 的 `runtime_id` 还是连接级临时 ID，跨连接复用会进一步导致会话无法重新定位。

修订版行为：

- `score-query` 直接复用任务内 `job-context.json`，校验缓存与 `source_hash`，不重新打开岗位详情。
- 批量候选人采集改为单个 UIA 会话：进入“消息”后只选择一次岗位和“新招呼”，随后按当前列表行逐个打开详情。
- 每个详情只读取右侧详情/聊天面板，排除左侧其他候选人列表文本，避免画像串人。
- 身份证据使用“当前点击行指纹 + 右侧唯一姓名 + 当前岗位 + mid-* 会话锚点”；任一项不唯一仍安全停止，不按姓名合并。
- 不发送消息、不求简历、不下载简历，不改变原有只读边界。


## v2 重构：完整事实采集与可解释输出（本地实施版）

本 Skill 已改为证据保留优先。批量或单人采集时，候选人详情面板中所有安全可见文本必须保存到 `profile.raw_profile_texts` 与 `profile.raw_profile_text`；旧的 `education`、`major`、`experience_summary` 等字段仅是兼容索引，不再是唯一信息源。

### 强制采集要求

- 在评分前完整保留当前候选人详情/聊天面板的安全可见文本，不得只挑选能命中 rubric 的行。
- 页面可见的学校、专业、学历、时间、在读/毕业状态必须保留原文。
- 页面可见的公司、岗位、起止时间、职责、项目、贡献和成果必须保留原文，多段经历不得合并为一句。
- 项目、技能、工具、到岗信息、自我介绍及其他与岗位有关的事实同样保留。
- 年龄、性别、照片、联系方式、住址、婚育等与岗位无关或敏感信息仍不得进入面向用户的评分结果。

### 完整性与失败语义

- 新快照必须有非空 `raw_profile_texts`、`raw_profile_text` 和 `visible_text_count`。
- 原文存在但兼容字段为空，不得把候选人事实判为不存在；评分从完整原文中取证。
- 后续追问学校、专业或经历时，必须优先读取已保存的 `candidate_information.raw_profile_texts`，不得无必要重新操作 BOSS。

### 强制评分输出

`score-query` 每位候选人必须输出：

- `candidate_information`：按教育、经历、项目、技能、到岗及其他事实分类，同时完整保留 `raw_profile_texts`。
- `assessment.evidence[]`：每项包含 `jd_requirement`、`candidate_field`、`candidate_facts`、`candidate_source_texts`、结论、权重与置信度。
- `assessment.calculation`：已知权重、总权重、已知得分点和公式。

禁止只输出“本科及以上”“有实习经历”。例如学历匹配时，必须同时输出快照中实际保存的学校、专业、学历和时间原文；实习匹配时，必须同时输出公司、岗位、时间、职责、项目及成果原文（页面存在时）。

### 本地版本说明

本地重构版保留现有 BOSS 1.7.4.963 只读 UIA 路径，并升级快照与结果契约。由于底层 `boss_candidates` wheel 仍为 0.4.3，本 Skill 通过本地 runtime wrapper 在创建快照前补充完整原文，不覆盖全局 wheel。


## 修订说明（任务附件修改版）

- 删除 180 秒固定总时限；保留最大滚动轮数、顶部/底部无变化判定和有限 `limit`，防止无限遍历。
- `score-query` 新增必填 `--job-context-file`，同一任务失败重试复用已经核验的 JD，不再进入“职位”页。
- JD 唯一来源改为 BOSS“职位 → 开放中 → 精确标题 → 编辑页只读回读”；删除本机发布记录优先路径。
- 其余固定边界不变：候选人只从消息入口采集；批量只用新招呼；不按姓名合并；不发消息、不求简历、不下载简历；保留 UIA 语义定位、岗位精确匹配、候选人身份与快照哈希校验。
