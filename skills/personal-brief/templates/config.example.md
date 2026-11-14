# 运行配置

这是私人运行配置，不提交到公共仓库。偏好与个人背景分别读取 preferences.md 和个人信息.md；用户明确完成或纠正记录读取 user-facts.md。

- data: {{data_dir}}
- skill: {{skill_dir}}
- preferences_file: preferences.md
- personal_information_file: 个人信息.md
- user_facts_file: user-facts.md
- timezone: 请填写 IANA 时区，例如 Asia/Shanghai
- mode: manual；默认不启用定时任务
- collector_model: 使用宿主可用模型，由用户选择
- collector_reasoning: 使用宿主默认值，由用户选择
- organizer_model: 使用宿主可用模型，由用户选择
- organizer_reasoning: 使用宿主默认值，由用户选择
- production_collector_thread_id: 未绑定
- production_organizer_thread_id: 未绑定
- production_host_id: 未绑定
- transcript_root: 未配置
- mail_helper: {{skill_dir}}/scripts/read_mail.py
- mail_accounts: mail-accounts.json（初始化为空账号列表，无凭据）
- reminders_adapter: 未配置；没有可用写入能力时只导出 Markdown
- reminders_list: 未配置；由用户指定专用列表

账号授权通过本机安全凭据存储完成，不在本文件写密码。正式定时运行前核对宿主能力、模型、会话绑定及提醒权限。来源与时段以 preferences.md 为准。
