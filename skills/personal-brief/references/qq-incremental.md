# QQ 列表增量判断

QQ 使用 `source_checks.chat_decision(current, previous)` 的 QQ 分支（current.source 必须为 QQ），优先于 collect-session.md 中其他聊天源的保守预览规则。是否有新增与历史正文是否全部读完分开记录；列表无变化不代表历史缺口已解决。

## 每轮列表观测

先扫描授权列表，在本轮完整范围内检查同名，保留每个位置的独立观测。不能用显示名作为 dict 唯一键吞掉重复项。current 字段：

- source: QQ；authorized: true/false；identity_key：沿用本地 source id，不把位置或显示时间加入 ID。
- identity_match：有界面稳定身份时 stable_id；本轮及既有来源均只有一个同名、会话类型等可见特征没有冲突时 unique_local；同名、改名或矛盾为 ambiguous。unique_local 是可复用的本地匹配，不冒充平台账号 ID。
- displayed_time：当前列表原样标签；observed_at：该观测实际时刻，ISO 带时区。工具把今天/昨天/星期/月日转换为日期或分钟区间，以各自 observed_at 解释，避免跨午夜仅因标签变了反复读取。
- preview：实际观察到的完整列表预览，保留发送者/附件名等文字，不手工缩写。preview_observed：确实获取到为 true；空预览与获取失败分开。preview_kind：text/image/file/emoji/call/empty 等固定类型。未读数可见时保存 unread_count；看不到不要编造 0。可见新活动提示可记 change_signal:true。

previous 是 SQLite 原 sources 记录。成功核对后保存 `accepted_list_observation`，内容为该次完整 current 加 `acceptance: body_checked`。首次授权仅建列表基线时用 initial_list_baseline，不能把增量中遗漏的正文伪装成首次基线。

## 判断与提交

- unchanged：同一会话、同一时间范围、相同预览/类型，双方观测都已晚于该显示时间范围，且无已知新活动或未完成的增量。可跳过正文，保留 body boundary；更新当前 list_observation 和观测时间。旧图片、截断预览或日期标签不再单独导致反复进入。
- needs_read：实际变化、未读数增加、同名歧义、时间不能解释、同一分钟/同一天仍可能藏新消息，或没有可信观测。进入核对到旧边界/实际末条。不能只凭未读标记决定是否读。
- 核对成功后重取列表，确认核对期间没有再变化，保存 accepted_list_observation，pending_incremental:false；正文未读完/受阻则 pending_incremental:true，并保留旧 accepted 快照，不把失败观测升级为已处理。
- unchanged 时可以把新的等价观测作为 accepted 快照继续保存，保留原 acceptance 和 checked_at；这只更新列表观测，绝不推进正文 boundary。
- 旧 gaps 分清 historical_gaps（已知旧空白、未开附件等）与 pending_incremental（新变化没有处理完）。不得只因存在任何历史缺口每轮重开同一聊天，也不能把尚未处理的新消息降级为历史缺口。

## 老记录与复测

旧记录缺 accepted_list_observation 时，仅当历史证据确实有完整同次列表预览、观测时间和正文/首次基线依据，才可迁移；不把手写节选冒充完整快照，不把后来 observed_at 套到旧“昨天”。否则本轮核对一次建立快照。

复测需包含同一会话的两次独立列表观测：第一次完成所需核对并入库；第二次重新读取真实列表，在输入未变时应判 unchanged 并且不点击正文。只把同一份 JSON 调两次是单元测试，不是实际复测。报告 list_checked / unchanged_skipped / needs_read / opened / pending，分别标明缓存建立和第二次读取；各来源是否启用由用户的私人配置决定。

每完成一小批核对就通过 brief_store.py 保存来源观测及判定证据，并在本轮 collection 报告记录 A/B 当前阶段和剩余范围。切换阶段前先落盘；不能把整轮结果只放在临时 CUA 变量中。恢复上下文时先核对本轮 run-id/锁和阶段，继续当前人工测试，不把生产配置误当成新的调度触发。
