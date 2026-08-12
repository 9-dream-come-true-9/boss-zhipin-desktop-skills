---
name: boss-job-publishing
description: 通过内置 pywinauto 函数，在 BOSS 直聘 Windows 桌面客户端填写、核验并安全发布实习生招聘、社招全职、应届校园招聘和兼职招聘岗位。四类岗位共用导航、职位名称、职位描述、地址、电话交换、回读核验、发布与结果核对流程，并根据 recruitment_type 处理各招聘类型专属字段。
---

# BOSS 直聘职位发布（实习生招聘 / 社招全职 / 应届校园招聘 / 兼职招聘）

只通过 bundled `scripts/boss_jobs.py` 在全新 Python 进程中调用 `boss_zhipin` 公开函数。不要使用 Python REPL、长期驻留解释器、临时 pywinauto、固定坐标、截图点击或固定次数方向键。

## 边界

- 支持四种招聘类型：`实习生招聘`、`社招全职`、`应届校园招聘`、`兼职招聘`。必须根据 `recruitment_type` 进入对应字段分支，不得把某一类型的专属字段套用到其他类型。
- 四类招聘共用职位入口、标题精确联想、职位描述、账号地址、电话交换助手、逐字段回读、发布授权、at-most-once 提交和结果核对规则。
- 招聘类型专属字段分别处理：实习使用学历、日薪、实习月数和每周到岗天数；社招使用经验、学历和月薪；校招使用固定经验、学历、月薪和毕业时间；兼职使用经验、学历、结算方式、四单位薪资、兼职时间、条件班次和招聘截止日期。
- 只接受本 Skill 已定义并能完整校验的四类字段组合；缺少对应分支必填字段、字段跨类型混用或平台目录值无效时安全失败，不猜测、不降级到其他招聘类型。
- 填写职位名称并选择完全一致的联想项。
- 不操作、输出或验证“职位类型”；它由 BOSS 根据名称联想项自动处理。
- “职位关键词 [选填]”始终跳过，不打开、不填写、不验证。
- 工作地址只使用账号已有地址：优先保留并回读预填地址；若未预填，只在地址选择器中恰好存在一个保存地址时选择它。没有或存在多个保存地址时安全失败，绝不新增或猜选地址。
- “请填写真实有效地址，若查实造假，将受到平台处罚。”是常驻说明文本，不操作、不验证，也不把它当成地址成功或表单就绪证据。
- `prepare` 负责填写和复核。用户要求“发布职位”“创建职位”或“按要求完成职位发布”，都已经授权最终发布；除非用户明确说“只填写”“只检查”或“不要发布”，全部字段回读通过后必须立即调用 `publish-reviewed`，不得暂停等待回复，也不得再次询问是否发布。
- 完整有效表单点击“发布”会直接提交，不会再出现确认弹窗。精确的 `Button(name="发布")` 就是最终提交边界，只允许调用一次；不要点击后等待或探索一个不存在的二次确认弹窗。

## 初始化

每个新任务在第一次 UI 操作前运行：

```powershell
python "<skill_dir>\scripts\ensure_runtime.py"
python "<skill_dir>\scripts\boss_jobs.py" runtime
```

两条命令都必须成功，且输出必须同时包含：

- `runtime_version=0.8.0`
- `runtime_build_id=boss-job-publishing-20260812-internship-social-campus-parttime-v1`
- `selector_profile=boss-1.7.4.963-native-uia-four-recruitment-v1`

不要在已经导入过旧包的进程中重试。`boss_jobs.py` 的每次调用都是新的系统进程，并会拒绝版本、build ID、selector profile 或模块来源不一致的运行时。

环境诊断只在失败时执行：

```powershell
python "<skill_dir>\scripts\boss_jobs.py" inspect
```

要求 BOSS 桌面端已启动、已登录且只有一个可见主窗口。若
`semantic_accessibility=False`，先等待页面加载；不要改用盲点坐标，也不要把未发布职位提示误判为可访问性故障。

## 进入发布表单：固定函数

bundled pywinauto 函数已按 BOSS Windows 客户端 `1.7.4.963` 固定以下路径：

1. 用 UIA 原生属性条件定位 `Hyperlink(title="职位")` 并进入职位页。
2. 精确定位 `Text(title="发布职位")`，验证其父控件是可见 `Button` 后点击；不依赖可能变化的私有图标字符。
3. 若出现“检测到您有未发布的职位，是否继续上次的编辑”，函数用
   `Text(title="重新发布")` 直接点击“重新发布”。
4. 等待弹窗消失，并要求“招聘类型”与职位名称输入框连续稳定后才返回。
5. 若已在滚动后的发布表单中，直接复用该表单；若意外出现“内容尚未保存，确定放弃？”，固定点击“取消”以保留表单，不离开页面。

这段路径不让 Agent 重新探索控件，也不使用坐标。只要出现上述未发布职位提示，就无条件点击“重新发布”，不向用户确认；这不是最终发布动作。不要为该提示设置
`restart_for_accessibility=True`，正常准备始终保持 `False`。

仅诊断入口时可调用：

```powershell
python "<skill_dir>\scripts\boss_jobs.py" open-form --timeout 30
```

## 构造实习职位

从用户消息或附件提取：

- 职位名称：2–20 字。
- 职位描述：10–5000 字，保留原始段落、换行和空格。
- 学历：`不限`、`初中及以下`、`中专/中技`、`高中`、`大专`、`本科`、`硕士` 或 `博士`。
- 日薪上下限：10–1000 的 10 元倍数，且下限小于上限。
- 最少实习月数：1–12。
- 每周最少到岗天数：1–7。
- 电话交换助手：仅在用户明确指定时传 `True` 或 `False`。
- 预期公司名称：可选；用户明确提供时用于校验，否则传 `None` 并回读当前账号公司。

将当次数据写入 Skill 目录之外的 UTF-8 临时 JSON：

```json
{
  "recruitment_type": "实习生招聘",
  "title": "<job_title>",
  "description": "<job_description>",
  "education": "<education>",
  "salary": {
    "unit": "元/天",
    "minimum": "<daily_salary_min_integer>",
    "maximum": "<daily_salary_max_integer>"
  },
  "internship": {
    "minimum_months": "<minimum_internship_months_integer>",
    "days_per_week": "<minimum_days_per_week_integer>"
  },
  "address": {
    "mode": "account_default"
  },
  "phone_exchange": "<true_false_or_null>",
  "expected_company": "<company_name_or_null>"
}
```

写入临时文件前，用本次请求的真实 JSON 类型替换全部占位符；不要保留示例值，也不要把任何一次招聘要求写回 Skill。

每次运行都重新从当前请求提取这些变量；不要复用历史职位、示例文件或上一次表单的业务值。
除可选的 `expected_company_or_none` 外，缺少任何必填业务字段时先向用户补齐。
不要为缺失字段猜测平台选项。不要把 QQ、微信、电话号码或平台禁止内容写入名称和描述。

## 构造社招全职职位

社招全职与实习职位共用上述通用字段与安全规则，只替换招聘类型相关字段：

- 招聘类型：`社招全职`。发布表单默认即为社招全职，只回读，不执行招聘类型切换动作。
- 经验：`不限`、`1年以内`、`1-3年`、`3-5年`、`5-10年` 或 `10年以上`。
- 学历：与实习职位相同。
- 月薪上下限：1–100 的整数，且下限小于上限，单位为 `月薪K`。
- 不使用 `internship` 字段。

临时 JSON：

```json
{
  "recruitment_type": "社招全职",
  "title": "<job_title>",
  "description": "<job_description>",
  "experience": "<experience>",
  "education": "<education>",
  "salary": {
    "unit": "月薪K",
    "minimum": "<monthly_salary_min_integer>",
    "maximum": "<monthly_salary_max_integer>"
  },
  "address": {
    "mode": "account_default"
  },
  "phone_exchange": "<true_false_or_null>",
  "expected_company": "<company_name_or_null>"
}
```

每次运行仍按原规则从当前请求提取变量；不要把示例或历史职位写回 Skill。

## 构造应届校园招聘职位

应届校招与其他分支共用标题、描述、地址、电话助手、证据和发布安全规则；招聘类型相关字段为：

- 招聘类型：`应届校园招聘`，运行时精确点击该类型并等待“毕业时间”字段出现。
- 经验：平台固定为 `在校/应届`，只回读，不执行经验切换。
- 学历：与其他分支相同。
- 月薪上下限：1–100 的整数，且下限小于上限，单位为 `月薪K`；使用主表单“薪资范围”两个下拉，不打开社招“薪资详情”弹窗。
- 毕业时间：必填起止范围 `graduation_year_start` 与 `graduation_year_end`。起始仅允许固定目录 `不限`、`2025`、`2026`、`2027`、`2028`；结束由起始联动，年份起始只允许同年或次年，起始“不限”时结束也必须“不限”。运行时严格先写起始、再写结束，并分别回读。
- 招聘截止时间为平台选填字段，本 Skill 始终跳过。
- 不使用 `internship` 字段。

临时 JSON：

```json
{
  "recruitment_type": "应届校园招聘",
  "title": "<job_title>",
  "description": "<job_description>",
  "experience": "在校/应届",
  "education": "<education>",
  "salary": {
    "unit": "月薪K",
    "minimum": "<monthly_salary_min_integer>",
    "maximum": "<monthly_salary_max_integer>"
  },
  "graduation_year_start": "<platform_start_year>",
  "graduation_year_end": "<platform_end_year>",
  "address": {"mode": "account_default"},
  "phone_exchange": "<true_false_or_null>",
  "expected_company": "<company_name_or_null>"
}
```

每次任务必须从当前请求构造临时规格；不要把任何测试职位值写入 Skill 包。

## 准备并回读

为同一次职位意图生成稳定的 `idempotency_key`，所有安全重试均复用它：

```powershell
python "<skill_dir>\scripts\boss_jobs.py" prepare `
  --spec-file "<temporary-spec.json>" `
  --idempotency-key "<stable-key-for-this-posting-intent>" `
  --timeout 30
```

`prepare_job_post` 只执行以下动作：

1. 按招聘类型处理字段入口：实习和应届校招精确切换；社招全职只回读默认“社招全职”，不切换。
2. 输入职位名称；即使重试时标题已经相同，也会先清空再写入，以重新触发联想。只通过 UIA 语义模式激活完全一致的联想项；找不到时安全失败。
3. 使用 ValuePattern 输入职位描述并逐字回读；不占用剪贴板。
4. 在当前活动下拉列表内按精确文本选择招聘类型对应字段：实习为学历、日薪、月数和天数；社招全职为经验、学历及“薪资详情”月薪；应届校招为学历、主表单月薪及毕业时间起止范围，并回读固定经验“在校/应届”。优先调用 `InvokePattern`，再尝试 `SelectionItemPattern`，绝不物理点击可能被裁剪的选项。
5. 保留账号预填地址；未预填时只选择账号唯一保存地址。电话交换助手通过 `TogglePattern` 设置并做语义状态回读。
6. 跳过职位类型和职位关键词。
7. 回读每个已操作字段。任务要求完成发布且全部 `verified=true` 时，立即执行下方发布函数。

将公司、标题、描述、招聘类型对应字段、地址、电话助手状态及每项
`expected / actual / verified` 作为内部发布证据。任务要求发布且全部
`verified=true` 时，不得在这里向用户展示后等待回复；立即发布，完成后再报告结果。
任一字段不一致时停止并报告，不得发布。

## 按任务要求发布

当前任务要求发布且字段回读全部通过后，立即调用一个固定函数：

```powershell
python "<skill_dir>\scripts\boss_jobs.py" publish-reviewed `
  --run-id "<run_id>"
```

`publish-reviewed` 在内部签发短时授权令牌、再次逐字段回读并跨越 at-most-once
提交边界；不要求用户再次确认。完整表单点击“发布”后会直接提交，没有二次弹窗。
最终点击函数先聚焦 BOSS，再重新解析 UIA 控件；要求工作地址输入框、规范链接、电话
CheckBox、表单锚点和精确 `Button(name="发布")` 同属唯一活动 `Document`。
作用域内按钮不是恰好一个、不可用或不支持 `InvokePattern` 时安全失败。唯一按钮只调用
一次 `InvokePattern`，不使用 `click_input`、截图、坐标或视觉识别。

**注意**：不要要求用户手动点击“职位 → 发布职位”，也不要退回坐标操作。不要向用户询问是否发布。

## 结果未知

若返回 `PublishOutcomeUnknown` 或状态为 `COMMIT_UNKNOWN`，禁止再次准备或点击发布，只执行：

```powershell
python "<skill_dir>\scripts\boss_jobs.py" reconcile --run-id "<run_id>"
```

只有明确的“发布成功”界面证据才会标记成功；同名历史职位不能证明本次提交成功。

## 错误处理

- `ValidationError`：纠正输入，不启动 UI。
- `AccessibilityUnavailable`：停止，不使用坐标或 OCR 盲点。
- `ElementNotFound`：保留页面并报告缺失的语义控件。
- `ReadbackMismatch`：报告字段的期望值与实际值，不发布。
- `ConfirmationInvalid`：若尚未进入提交边界，重新准备并回读；原任务仍要求发布且全部一致时直接再次调用 `publish-reviewed`，不得询问用户。若已是 `SUBMITTING` 或 `COMMIT_UNKNOWN`，只执行核对。
- `PublishOutcomeUnknown`：只核对，绝不重发。

同一 BOSS 窗口只允许一个任务串行操作。失败时报告 runner 输出中的 runtime provenance、`run_id`、状态、`error_details.code` 和诊断目录。入口失败时允许等待页面后用新的 `boss_jobs.py` 进程重试一次


## 兼职招聘字段规则（0.8.0）

兼职招聘必须提供 `experience`、`education`、`salary` 和 `part_time`：

```json
{
  "recruitment_type": "兼职招聘",
  "experience": "不限",
  "education": "不限",
  "salary": {"unit": "元/时", "minimum": 20, "maximum": 30},
  "part_time": {
    "settlement": "周结",
    "work_date": "2个月",
    "work_period": "周末节假日",
    "days_per_week": "3-4天",
    "work_hours": "不限时间",
    "recruitment_deadline": "YYYY-MM-DD",
    "shifts": []
  }
}
```

固定平台目录：

- `settlement`：日结、周结、月结、完工结。
- `salary.unit`：元/时、元/天、元/周、元/月。金额必须来自运行时内置的平台目录，且最高必须严格大于最低。
- `work_date`：1个月、2个月、3个月、6个月、长期兼职。
- `work_period`：工作日、周末节假日、全周轮班、按单安排时间、不限时间。
- `days_per_week`：5天及以上、3-4天、2-3天、1-2天、无要求。
- `work_hours`：不限时间、按班次。
- 当 `work_hours=按班次` 时，`shifts` 必填且至少一项，只允许早班、午班、晚班、夜班；其他工作时间模式禁止提供 `shifts`。
- `recruitment_deadline` 必须是 `YYYY-MM-DD` 且不早于运行当天。

运行时将兼职时间写入后从 UIA `ValuePattern` 回读完整摘要。班次在摘要中编码为早班=1、午班=2、晚班=3、夜班=4；如草稿残留其他班次，函数会按实际编码与目标集合的对称差异进行校准，再次回读确认。
