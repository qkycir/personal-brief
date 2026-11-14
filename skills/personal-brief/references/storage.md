# SQLite 与 Markdown

`<data>/brief.sqlite3` 是动态记录的唯一正式存储。`config.md`（运行配置）、`preferences.md`（偏好）、`个人信息.md`（背景）和可选 `user-facts.md`（明确用户确认）是可编辑输入，不从数据库覆盖。原邮件、截图与录音留在私人目录中，数据库只存必要摘录、定位及路径。凭据使用宿主安全存储；随附 macOS 邮箱适配器使用钥匙串。

使用本 Skill 的 `scripts/brief_store.py`，Python 标准库，无常驻服务。命令中的 `<skill>` 与 `<data>` 必须替换为本轮绝对路径：

```sh
python3 <skill>/scripts/brief_store.py --data-dir <data> init
python3 <skill>/scripts/brief_store.py --data-dir <data> query events
python3 <skill>/scripts/brief_store.py --data-dir <data> query sources --id wechat:local-identity
python3 <skill>/scripts/brief_store.py --data-dir <data> apply <data>/runs/<run-id>/batch.json
python3 <skill>/scripts/brief_store.py --data-dir <data> check
python3 <skill>/scripts/brief_store.py --data-dir <data> ready --run-id <run-id> --phase partial
python3 <skill>/scripts/brief_store.py --data-dir <data> export
```

`query` 也支持 `--run-id`，但增量整理须同时查相关历史事件和已有任务。apply 接收 JSON 对象，键为以下类别，值为对象数组；所有对象都有稳定 `id`。一批在一个事务内写入，失败全部回滚；同 ID 相同内容为无操作。`revisions` 自动记录变更前后。不能用临时 SQL 绕过校验。JSON 是提交材料，SQLite 是正式状态；MD 是自动导出，不再独立编辑同一份状态。

## 对象字段

- **events**：`id, run_id, source_key, title, source, locator, source_time, observed_at, excerpt, summary, body_complete`（布尔）, `applicability`。其他证据字段按 records.md 保存。`source_key` 是同一来源事实的去重键：有原始消息 ID 时用它，否则组合会话区分信息、发送者、原始时间、原文与事件子项；优先 SHA256。不要把运行时间放进键，不以显示名或预览哈希单独代替消息身份。一个通知的不同事项使用不同子项键；跨来源合并在任务层完成。若 source_key 已存在，query 找到原 id 更新，不能换 id 重插。
- **sources**：`id, source, observed_at, coverage, boundary`；可加 `display_name, identity_status, displayed_time, preview, preview_sha256, unread_before, unread_after, gaps`。每个会话/文件一条，渠道汇总另行一条。显示名相同不代表同一会话，没有稳定身份时保留独立观测和 `identity_status: ambiguous`，下次用界面核对。指纹只是变化提示，不是唯一 ID。首次微信只建 metadata 基线，禁止为消歧读取旧正文；保留歧义到允许增量核对时解决。
- **processed_mail**：`id, run_id, cache_path, uidvalidity, uid, event_ids`。id 组合账号/文件夹/UIDVALIDITY/UID。没有相关事件也登记空数组并说明过滤理由。先读完整邮件缓存，再把事件和处理记录同批 apply。抓取游标在 sources 的 `mail:<account>|<folder>`；read_mail.py 自动维护。不得手动重置正常游标。
- **verifications**：`id, run_id, event_ids, result`（pass/pending/reject）, `verified_at, evidence`。evidence 包括原文入口、日期归属、原文摘录、适用/完成/条件检查、必要截图路径。核验是回原始来源，非检查 JSON 格式。
- **tasks**：`id, run_id, title, state`（candidate/active/completed/cancelled/pending/withdrawn_invalid_source）, `event_ids`。实际提醒另需 `verification_id, reminder_id, last_synced_content`（工具读回快照）；active 必须引用覆盖全部 event_ids 的 pass 核验。还记录 `deadline/activity_date, alarm, date_role, date_precision, catch_up_alarm_consumed` 等。稳定 id 跨轮保留，用户完成不得自动复活。
- **documents**：`id` 为导出路径，`body` 为 Markdown 正文，可带 run_id。允许 `profile.md, focus.md, status.md, runs/<run-id>/collection.md, runs/<run-id>/organize.md` 等；events/source-state/tasks/mail-processed 是结构化表自动导出，不能另写 documents 覆盖。verification.md 自动由核验表导出，handoff 用 ready 生成。
- **runs**：`id` 为 run-id，`phase`，`coverage`（各渠道覆盖和缺口）；可带模式/起止时间/线程 ID。collecting 开始，采集后 `ready` 校验并置 collected/partial，最后 organizer 置 organized/partial_organized。
- **receipts**：`id, task_id, kind, at`；外部提醒补发等操作回执。测试重置时保留已发送通知回执，避免重复弹窗；不能把回执当原文采集结果。

所有规范时间字段只允许 `YYYY-MM-DD`、带明确时区的 `YYYY-MM-DDTHH:MM:SS+08:00` 或 `unknown`。observed_at、verified_at 必须为带时区时刻。解释文字写在 `time_note` 等独立字段；不追加第二个时区。邮件 Date 用 `email.utils.parsedate_to_datetime(...).astimezone(ZoneInfo(...)).isoformat()` 一次生成。原始不精确时间保留为 `displayed_time` 或 `raw_time`，不编造秒/分钟精度的意义。原文无法辨认才使用 unknown，不能为通过校验抹掉已知日期。

## 提交顺序

采集：登记 run → 分批事件+每来源成功边界 → collection 报告 → ready。部分失败保留 gaps，不能用结束时间推进未读范围。工具错误必须处理后重试，成功 ready 才交接。

整理：查 run 的 ready 标记、events/tasks 和用户信息 → 原文核验入库 → 候选任务入库 → 外部提醒读回并对账 → 保存 reminder_id/snapshot 和回执 → profile/focus/status/organize 文档入库 → export。外部 Apple 写入与 SQLite 不是同一事务：先保存候选及预定内容，异常后先列出提醒对账，不能盲目再次 add。任务命名/备注不能藏内部 ID；关联只存在数据库。恢复时用候选标题、截止、简短来源与完整快照比对，歧义留给协调者。

新 session 以 SQLite 的 ready 和记录为准；MD 可供阅读但不是另一份真相。用户直接修改 `个人信息.md` 始终有效。画像导出仅包含有来源的候选背景，不自动写回用户信息。

`check` 同时检查结构、事件引用和 active 任务的核验关联；已结束或中止的 run 不能再次 ready。被拒绝的批次不推进事件或来源状态。Markdown 导出失败而 SQLite 已提交时，先查询实际状态，再重试 export，不重做外部提醒写入。更新同一事件沿用稳定 id 并关联原事件，自动 revisions 保留修改前内容；已交接轮次的日期证据应以当轮 verification/原始缓存为准，不用后改的 events 内容冒充当时证据。
