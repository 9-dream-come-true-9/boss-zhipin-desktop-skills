---
name: boss-job-publishing
description: 通过内置 pywinauto 函数在 BOSS 直聘 Windows 桌面客户端填写、核验并直接发布实习岗位。适用于 Codex 处理“实习生招聘”：从消息或文本文件提取岗位信息，填写职位名称、描述、学历、日薪、实习时长、每周到岗天数、账号默认地址和电话交换字段；当任务要求完成发布时，在回读验证无误后自动发布，或核对提交结果不确定的状态。
---

# BOSS 直聘实习职位

只通过 bundled `scripts/boss_jobs.py` 在全新 Python 进程中调用 `boss_zhipin` 公开函数。不要使用 Python REPL、长期驻留解释器、临时 pywinauto、固定坐标、截图点击或固定次数方向键。

## 边界

- 只允许 `实习生招聘`；拒绝社招、校招和兼职。
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

- `runtime_version=0.4.3`
- `runtime_build_id=boss-job-publishing-20260731-semantic-publish-v5`
- `selector_profile=boss-1.7.4.963-native-uia-semantic-publish-v5`

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

## 准备并回读

为同一次职位意图生成稳定的 `idempotency_key`，所有安全重试均复用它：

```powershell
python "<skill_dir>\scripts\boss_jobs.py" prepare `
  --spec-file "<temporary-spec.json>" `
  --idempotency-key "<stable-key-for-this-posting-intent>" `
  --timeout 30
```

`prepare_job_post` 只执行以下动作：

1. 切换到实习生招聘。
2. 输入职位名称；即使重试时标题已经相同，也会先清空再写入，以重新触发联想。只通过 UIA 语义模式激活完全一致的联想项；找不到时安全失败。
3. 使用 ValuePattern 输入职位描述并逐字回读；不占用剪贴板。
4. 在当前活动下拉列表内按精确文本选择学历、日薪、月数和天数；优先调用 `InvokePattern`，再尝试 `SelectionItemPattern`，绝不物理点击可能被裁剪的选项。
5. 保留账号预填地址；未预填时只选择账号唯一保存地址。电话交换助手通过 `TogglePattern` 设置并做语义状态回读。
6. 跳过职位类型和职位关键词。
7. 回读每个已操作字段。任务要求完成发布且全部 `verified=true` 时，立即执行下方发布函数。

将公司、标题、描述、学历、日薪、实习要求、地址、电话助手状态及每项
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

**注意**：不要要求用户手动点击“职位 → 发布职位”，也不要退回坐标操作。不要向用户询问受否发布

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
