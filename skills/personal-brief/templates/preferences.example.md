# 偏好配置

所有来源初始关闭。用户确认读取范围后再启用；示例值不是读取授权。

## QQ
- enabled: false
- include_conversations: []
- exclude_conversations: []
- first_read: 待选择：仅建基线，或指定会话及回看天数
- incremental: 只处理授权范围内的新增与变更
- max_conversations: 待用户指定
- schedule_local: []

## 微信
- enabled: false
- include_conversations: []
- exclude_conversations: []
- first_read: 仅建立授权范围内的列表基线，不读旧正文
- max_conversations: 待用户指定；按列表位置计数，排除项也计入
- schedule_local: []
- catch_up_outside_schedule: false
- login_failure: 停止该来源，不自动登录或重试

## 朋友圈
- enabled: false；不随微信聊天启用而自动启用

## 邮箱与逐字稿
- mail_enabled: false
- mail_first_lookback_days: 由用户指定
- mail_folders: []
- transcripts_enabled: false
- transcripts_first_lookback_days: 由用户指定

## 重要性与通知
- 必办、明确指派、已承诺的事项优先；普通推广或自愿活动通常只作背景。
- 不确定是否适用时列待确认，不猜个人身份或正式截止。
- 默认禁止发送消息/邮件、点赞、评论、通话；只在授权范围内恢复未读标记。
- schedule_local: []；初始仅手动运行
- reconcile: 每轮采集后都做轻量对账；有变化才深入处理。
- reminder_lead_time: 由用户指定
- date_only_alarm_local: 由用户指定
- catch_up_alarm: 初始关闭，由用户决定是否允许错过时刻后的补提醒
- reminder_notes: 行动所需内容、链接、来源和通知原始时间；内部ID及核验过程不展示
- 所有读取遇到锁屏、用户操作、安全提示或权限失败时停止对应路径并记缺口。
