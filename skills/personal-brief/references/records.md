# 本地记录契约

私人输入是 `config.md`、`preferences.md`、`个人信息.md`、可选 `user-facts.md`。动态记录以 `brief.sqlite3` 为准，`events.md`、`profile.md`、`focus.md`、`tasks.md`、`status.md`、`source-state.md` 和轮次报告均由存储工具导出；不要独立编辑这些动态Markdown。真实数据不进入公共Git仓库。

## 事件

events 表使用唯一稳定 id，events.md 是自动导出的视图。每条至少包含：
- 来源种类、会话/邮件/录音定位；source_time（原始时间）与 observed_at（采集时间）分开。
- 必要的原文片段、事实摘要、关联人/项目；不堆积无关私人正文。
- event_kind：request / deadline / schedule_change / cancellation / completion / background / user_confirmation。
- deadline：精确时刻、date-only、unknown 三者之一；保留原话，时区按配置。
- 活动日期另记activity_date与date_role=activity_date；活动日期已确认不等于存在精确办理截止。日期型活动提醒允许地点等附属字段unknown，但须注明这些未知字段，不替用户选择。
- applicability：明确与本人有关 / 待确认 / 可选；不要把广告、所有人的闲聊转换为任务。
- 关联事件 ID、变更记录、来源可信程度及缺口。后来的改期不能抹掉原依据。
- 日期证据：`message_time`、`is_quote`、`quoted_source_time`、`body_quote_boundary_verified`、原文时间表达及日期推算过程。无法确认的字段写unknown。引用内日期用原消息时间；当前正文日期用当前消息时间，两者不能合并。
- 条件性事件：记录 `condition`、`current_condition`（true/false/unknown）及核验来源。收件箱没有后续邮件不是条件成立的证据。

跨来源的同一任务可用多个事件相互关联；整理阶段决定合并，保留出处。界面没有稳定消息 ID 时用会话身份、发送人、时间及原文片段组合定位，重叠检查；不能声称精确全量。

## 采集状态与交接

`source-state.md` 记录各来源/会话最后成功边界、时间显示、末条预览或指纹、首次基线、未读恢复结果。只有读取到的范围才能推进，不可用本轮结束时间代替漏读区间。

每轮先登记 runs.phase=collecting；将渠道覆盖、缺口、事件 ID、未读恢复和下一步存入 collection 文档记录。最后调用 brief_store.py ready，校验后标为 collected/partial 并导出 handoff.md。部分成功可交接，未成功渠道必须显式列出。

整理阶段只消费明确完成交接的 run-id。`tasks.md` 每个任务保存稳定 task-id、关联 event-id、Apple reminder-id、标题、状态、截止精度、提醒时间和上次同步内容。用户手动修改/完成优先；不自动复活、删掉或覆盖。

`profile.md` 仅存稳定背景、长期目标、明确偏好并附事件依据；`focus.md` 存当前关注、等待、候选任务与缺口。第三方自述和 AI 推断分开，避免敏感属性猜测。

整理完成写 `runs/<run-id>/organize.md`，包括写入/更新/未写入的任务、验证结果、告警及个人配置需要确认的部分。不要将同一 run 重复处理为新任务。

同时维护 `verification.md`，逐个记录整理者回原始来源核对的证据与pass/pending/reject结论。历史工具读回仅证明写入成功，不能替代原文与当前状态核验。
