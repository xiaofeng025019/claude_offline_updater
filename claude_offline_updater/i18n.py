"""Internationalization support (Chinese/English)"""

import os

# Current language, defaults to English
_lang = os.environ.get("CLAUDE_UPDATE_LANG", "en")

LANGS = ("zh", "en")


def set_lang(lang: str):
    global _lang
    if lang in LANGS:
        _lang = lang


def get_lang() -> str:
    return _lang


# ── Translation dictionary ───────────────────────────────────────────────────
# key: translation ID, value: {zh: "Chinese", en: "English"}
_T: dict[str, dict[str, str]] = {
    # ── Main Menu ─────────────────────────────────────────────────────────
    "app_title":             {"zh": "Claude Code 离线更新工具", "en": "Claude Code Offline Updater"},
    "menu_prompt":           {"zh": "请选择操作:", "en": "Select action:"},
    "menu_scan":             {"zh": "扫描机器版本", "en": "Scan machine versions"},
    "menu_update":           {"zh": "更新Claude版本", "en": "Update Claude version"},
    "menu_history":          {"zh": "查看更新历史", "en": "View update history"},
    "menu_config":           {"zh": "查看/管理配置", "en": "View/manage config"},
    "menu_cache":            {"zh": "管理本地缓存", "en": "Manage local cache"},
    "menu_quit":             {"zh": "退出", "en": "Quit"},
    "goodbye":               {"zh": "再见!", "en": "Goodbye!"},

    # ── Scan ──────────────────────────────────────────────────────────────
    "scanning":              {"zh": "扫描机器...", "en": "Scanning machines..."},
    "scan_done":             {"zh": "扫描完成", "en": "Scan complete"},
    "scan_title":            {"zh": "扫描机器版本", "en": "Scan Machine Versions"},
    "scan_result_title":     {"zh": "机器版本扫描结果", "en": "Machine Version Scan Results"},
    "col_name":              {"zh": "名称", "en": "Name"},
    "col_host":              {"zh": "主机", "en": "Host"},
    "col_port":              {"zh": "端口", "en": "Port"},
    "col_version":           {"zh": "当前版本", "en": "Version"},
    "col_status":            {"zh": "状态", "en": "Status"},
    "status_latest":         {"zh": "已是最新", "en": "Up to date"},
    "status_need_update":    {"zh": "需更新", "en": "Needs update"},
    "status_not_installed":  {"zh": "未安装", "en": "Not installed"},
    "status_conn_failed":    {"zh": "连接失败", "en": "Connection failed"},

    # ── Version Query ─────────────────────────────────────────────────────
    "querying_version":      {"zh": "查询最新版本...", "en": "Querying latest version..."},
    "latest_version":        {"zh": "最新版本", "en": "Latest version"},
    "specify_version":       {"zh": "指定版本", "en": "Specified version"},
    "query_failed":          {"zh": "查询失败", "en": "Query failed"},
    "query_retrying":        {"zh": "查询失败，{attempt}/{max_retries} 次重试...", "en": "Query failed, {attempt}/{max_retries} retries..."},
    "version_unavailable":   {"zh": "无法获取最新版本信息", "en": "Cannot get latest version info"},
    "version_unavailable_retry": {"zh": "无法获取最新版本（已重试", "en": "Cannot get latest version (retried"},
    "version_times":         {"zh": "次）", "en": "times)"},

    # ── Download ──────────────────────────────────────────────────────────
    "downloading":           {"zh": "下载中...", "en": "Downloading..."},
    "download_cache_miss":   {"zh": "缓存未命中）", "en": "cache miss)"},
    "download_hit_cache":    {"zh": "命中本地缓存", "en": "Cache hit"},
    "download_complete":     {"zh": "下载完成", "en": "Download complete"},
    "download_failed":       {"zh": "下载失败", "en": "Download failed"},
    "download_retrying":     {"zh": "下载失败，{attempt}/{max_retries} 次重试...", "en": "Download failed, {attempt}/{max_retries} retries..."},
    "download_empty":        {"zh": "下载的文件为空", "en": "Downloaded file is empty"},
    "cached_to":             {"zh": "已缓存到", "en": "Cached to"},

    # ── Checksum ──────────────────────────────────────────────────────────
    "verifying_checksum":    {"zh": "获取清单文件进行 SHA256 校验...", "en": "Fetching manifest for SHA256 verification..."},
    "checksum_skip":         {"zh": "无法获取 manifest.json，跳过校验", "en": "Cannot fetch manifest.json, skipping verification"},
    "checksum_no_value":     {"zh": "manifest.json 中未找到校验值，跳过校验", "en": "No checksum in manifest.json, skipping verification"},
    "checksum_expected":     {"zh": "期望 SHA256", "en": "Expected SHA256"},
    "checksum_ok":           {"zh": "SHA256 校验通过", "en": "SHA256 checksum verified"},
    "checksum_fail":         {"zh": "SHA256 校验失败!", "en": "SHA256 checksum FAILED!"},
    "checksum_expected_lbl": {"zh": "期望", "en": "Expected"},
    "checksum_actual_lbl":   {"zh": "实际", "en": "Actual"},
    "network_unreachable":   {"zh": "下载服务器不可达，请检查网络连接", "en": "Download server unreachable, check network"},
    "network_skip_verify":   {"zh": "网络不可达，跳过 SHA256 校验", "en": "Network unreachable, skipping SHA256 verification"},

    # ── Deployment ────────────────────────────────────────────────────────
    "deploy_local":          {"zh": "执行安装...", "en": "Installing..."},
    "deploy_offline":        {"zh": "使用离线部署...", "en": "Using offline deployment..."},
    "deploy_failed":         {"zh": "部署失败", "en": "Deployment failed"},
    "deploy_local_failed":   {"zh": "本地部署失败", "en": "Local deployment failed"},
    "transferring":          {"zh": "传输文件...", "en": "Transferring file..."},
    "installing":            {"zh": "执行安装...", "en": "Installing..."},
    "verifying_version":     {"zh": "验证版本...", "en": "Verifying version..."},
    "version_verify_fail":   {"zh": "版本验证失败", "en": "Version verification failed"},
    "verify_failed":         {"zh": "验证失败", "en": "Verification failed"},
    "update_complete":       {"zh": "更新完成", "en": "Update complete"},
    "local_rollback":        {"zh": "已回滚到旧版本", "en": "Rolled back to previous version"},
    "local_rollback_err":    {"zh": "验证异常，已回滚到旧版本", "en": "Verification error, rolled back"},
    "remote_rollback":       {"zh": "已回滚到", "en": "Rolled back to"},
    "deploy_exception_rollback": {"zh": "部署异常，已回滚到", "en": "Deploy exception, rolled back to"},
    "parallel_deploy":       {"zh": "开始并行部署", "en": "Starting parallel deployment"},
    "remote_machines":       {"zh": "台远程", "en": "remote machines"},

    # ── Cleanup ───────────────────────────────────────────────────────────
    "cleaning_remote":       {"zh": "清理远程旧版本...", "en": "Cleaning remote old versions..."},
    "cleaning_local":        {"zh": "清理本地旧版本...", "en": "Cleaning local old versions..."},
    "clean_invalid":         {"zh": "删除无效版本", "en": "Removed invalid version"},
    "clean_old":             {"zh": "删除旧版本", "en": "Removed old version"},
    "kept_versions":         {"zh": "保留版本", "en": "Kept versions"},
    "remote_clean_done":     {"zh": "远程版本清理完成", "en": "Remote version cleanup complete"},
    "local_clean_done":      {"zh": "本地版本清理完成", "en": "Local version cleanup complete"},

    # ── Selection ─────────────────────────────────────────────────────────
    "select_prompt":         {"zh": "选择要更新的机器（空格选中/取消，回车确认）:",
                              "en": "Select machines to update (space to toggle, enter to confirm):"},

    "preview_title":         {"zh": "机器状态预览", "en": "Machine Status Preview"},

    # ── Update Flow ───────────────────────────────────────────────────────
    "will_update":           {"zh": "将更新", "en": "Will update"},
    "machines":              {"zh": "台机器", "en": "machines"},
    "update_summary":        {"zh": "将更新 {update} 台机器，{skip} 台已是最新", "en": "Will update {update} machines, {skip} already latest"},
    "all_latest":            {"zh": "所有选中机器已是最新版本", "en": "All selected machines are up to date"},
    "no_selection":          {"zh": "未选择任何机器", "en": "No machines selected"},
    "dry_run":               {"zh": "dry-run 模式，不执行实际更新", "en": "Dry-run mode, no actual updates"},

    # ── Results ───────────────────────────────────────────────────────────
    "result_title":          {"zh": "更新结果", "en": "Update Results"},
    "col_result":            {"zh": "结果", "en": "Result"},
    "col_detail":            {"zh": "详情", "en": "Detail"},
    "result_success":        {"zh": "✓ 成功", "en": "✓ Success"},
    "result_failed":         {"zh": "✗ 失败", "en": "✗ Failed"},
    "result_skipped":        {"zh": "─ 跳过", "en": "─ Skipped"},
    "result_already_latest": {"zh": "(已是最新)", "en": "(already latest)"},
    "total":                 {"zh": "总计", "en": "Total"},
    "success_count":         {"zh": "成功", "en": "Success"},
    "failed_count":          {"zh": "失败", "en": "Failed"},
    "skipped_count":         {"zh": "跳过", "en": "Skipped"},

    # ── History ───────────────────────────────────────────────────────────
    "history_title":         {"zh": "更新历史", "en": "Update History"},
    "col_time":              {"zh": "时间", "en": "Time"},
    "col_machine":           {"zh": "机器", "en": "Machine"},
    "col_version_change":    {"zh": "版本变更", "en": "Version Change"},
    "col_duration":          {"zh": "耗时", "en": "Duration"},
    "no_history":            {"zh": "暂无更新历史记录", "en": "No update history"},
    "history_filter":        {"zh": "查看哪台机器的历史？", "en": "View history for which machine:"},
    "all_machines":          {"zh": "全部", "en": "All"},

    # ── Operation Log ─────────────────────────────────────────────────────
    "oplog_title":           {"zh": "操作日志", "en": "Operation Log"},
    "oplog_no_records":      {"zh": "暂无操作日志记录", "en": "No operation log records"},
    "oplog_filter":          {"zh": "查看哪台机器的日志？", "en": "View log for which machine:"},
    "col_event":             {"zh": "事件", "en": "Event"},
    "event_update":          {"zh": "更新", "en": "Update"},
    "event_add":             {"zh": "添加", "en": "Add"},
    "event_remove":          {"zh": "删除", "en": "Remove"},
    "event_rename":          {"zh": "重命名", "en": "Rename"},
    "event_ip_change":       {"zh": "IP变更", "en": "IP Change"},
    "event_first_seen":      {"zh": "首次发现", "en": "First Seen"},
    "detail_renamed":        {"zh": "{old} → {new}", "en": "{old} → {new}"},
    "detail_ip_changed":     {"zh": "{old} → {new}", "en": "{old} → {new}"},
    "detail_first_seen":     {"zh": "发现机器ID: {mid}", "en": "Discovered machine ID: {mid}"},
    "oplog_type_all":        {"zh": "全部类型", "en": "All types"},
    "oplog_type_filter":     {"zh": "筛选事件类型:", "en": "Filter event type:"},

    # ── Config ────────────────────────────────────────────────────────────
    "config_action":         {"zh": "配置操作:", "en": "Config action:"},
    "config_edit_settings":  {"zh": "修改全局设置", "en": "Edit global settings"},
    "config_edit_local":     {"zh": "修改本机设置", "en": "Edit local settings"},
    "config_edit_machine":   {"zh": "编辑远程机器", "en": "Edit remote machine"},
    "config_add":            {"zh": "添加远程机器", "en": "Add remote machine"},
    "config_remove":         {"zh": "删除远程机器", "en": "Remove remote machine"},
    "config_set_lang":       {"zh": "设置语言", "en": "Set language"},
    "config_return":         {"zh": "← 返回", "en": "← Back"},
    "config_current_lang":   {"zh": "当前语言", "en": "Current language"},
    "config_select_lang":    {"zh": "选择语言:", "en": "Select language:"},
    "config_lang_changed":   {"zh": "语言已切换为", "en": "Language changed to"},
    "lang_zh":               {"zh": "中文", "en": "Chinese"},
    "lang_en":               {"zh": "English", "en": "English"},
    "machine_added":         {"zh": "已添加机器", "en": "Machine added"},
    "machine_exists":        {"zh": "机器", "en": "Machine"},
    "machine_exists_suffix": {"zh": "已存在", "en": "already exists"},
    "machine_removed":       {"zh": "已删除机器", "en": "Machine removed"},
    "machine_not_found":     {"zh": "未找到机器", "en": "Machine not found"},
    "no_machines":           {"zh": "没有配置任何机器", "en": "No machines configured"},
    "select_remove":         {"zh": "选择要删除的机器:", "en": "Select machine to remove:"},
    "select_edit_machine":   {"zh": "选择要编辑的机器:", "en": "Select machine to edit:"},
    "input_name":            {"zh": "机器名称:", "en": "Machine name:"},
    "input_host":            {"zh": "主机地址:", "en": "Host address:"},
    "input_port":            {"zh": "SSH 端口 (默认 22):", "en": "SSH port (default 22):"},
    "input_user":            {"zh": "SSH 用户 (默认 root):", "en": "SSH user (default root):"},
    "config_not_found":      {"zh": "配置文件不存在", "en": "Config file not found"},
    "config_default_path":   {"zh": "默认配置路径", "en": "Default config path"},
    "config_enabled":        {"zh": "已启用", "en": "enabled"},
    "config_disabled":       {"zh": "已禁用", "en": "disabled"},
    "config_init_hint":      {"zh": "可使用 config.yaml.example 作为模板", "en": "Use config.yaml.example as a template"},
    "config_auto_created":   {"zh": "已自动创建默认配置文件", "en": "Default config file auto-created"},
    "config_init_created":   {"zh": "配置文件已创建:", "en": "Config file created:"},
    "config_init_exists":    {"zh": "配置文件已存在:", "en": "Config file already exists:"},
    "config_init_prompt":    {"zh": "是否添加第一台远程机器？", "en": "Add your first remote machine?"},
    "config_welcome":        {"zh": "欢迎使用 Claude Code Offline Updater！首次运行，正在初始化配置...", "en": "Welcome to Claude Code Offline Updater! Initializing config for first run..."},
    "config_no_change":      {"zh": "未修改", "en": "No change"},

    # ── Config Display ────────────────────────────────────────────────────
    "config_panel_settings": {"zh": "全局设置 (Settings)", "en": "Global Settings"},
    "config_panel_local":    {"zh": "本机设置 (Local)", "en": "Local Settings"},
    "config_panel_machines": {"zh": "远程机器列表", "en": "Remote Machines"},
    "config_col_key":        {"zh": "配置项", "en": "Key"},
    "config_col_value":      {"zh": "当前值", "en": "Value"},
    "config_col_default":    {"zh": "默认值", "en": "Default"},
    "config_col_m_name":     {"zh": "名称", "en": "Name"},
    "config_col_m_host":     {"zh": "主机", "en": "Host"},
    "config_col_m_port":     {"zh": "端口", "en": "Port"},
    "config_col_m_user":     {"zh": "用户", "en": "User"},
    "config_col_m_id":       {"zh": "机器ID", "en": "Machine ID"},
    "machine_id_saved":      {"zh": "已保存机器ID", "en": "Machine ID saved"},
    "config_edit_prompt":    {"zh": "输入新值（留空保持不变）:", "en": "Enter new value (leave empty to keep):"},
    "config_field_desc":     {
        "zh": "字段说明",
        "en": "Field description",
    },

    # ── Cache ─────────────────────────────────────────────────────────────
    "cache_title":           {"zh": "本地二进制缓存", "en": "Local Binary Cache"},
    "cache_empty":           {"zh": "本地缓存为空", "en": "Local cache is empty"},
    "cache_col_version":     {"zh": "版本", "en": "Version"},
    "cache_col_platform":    {"zh": "平台", "en": "Platform"},
    "cache_col_size":        {"zh": "大小", "en": "Size"},
    "cache_col_path":        {"zh": "路径", "en": "Path"},
    "cache_total":           {"zh": "个缓存，总计", "en": "cache entries, total"},
    "cache_action":          {"zh": "缓存操作:", "en": "Cache action:"},
    "cache_clean_keep":      {"zh": "清理旧缓存（保留最新3个）", "en": "Clean old cache (keep latest 3)"},
    "cache_clean_all":       {"zh": "清空全部缓存", "en": "Clear all cache"},
    "cache_cleaned":         {"zh": "缓存清理完成，保留", "en": "Cache cleaned, kept"},
    "cache_cleaned_delete":  {"zh": "个，删除", "en": ", deleted"},
    "cache_all_cleared":     {"zh": "已清空全部缓存", "en": "All cache cleared"},
    "cache_dir_not_exist":   {"zh": "缓存目录不存在", "en": "Cache directory does not exist"},
    "cache_corrupted":       {"zh": "已删除损坏的缓存", "en": "Removed corrupted cache"},
    "cache_clean_entry":     {"zh": "清理缓存: claude-{version}-{platform} ({size_mb}MB)", "en": "Clean cache: claude-{version}-{platform} ({size_mb}MB)"},

    # ── PATH ──────────────────────────────────────────────────────────────
    "path_added":            {"zh": "已将 ~/.local/bin 添加到远程 .bashrc", "en": "Added ~/.local/bin to remote .bashrc"},
    "path_add_failed":       {"zh": "添加 PATH 到 .bashrc 失败，请手动配置", "en": "Failed to add PATH to .bashrc, configure manually"},

    # ── Install Method ────────────────────────────────────────────────────
    "install_method_set":    {"zh": "已设置 installMethod=native", "en": "Set installMethod=native"},
    "install_method_set_failed": {"zh": "设置 installMethod 失败", "en": "Failed to set installMethod"},

    # ── General ───────────────────────────────────────────────────────────
    "retries_suffix":        {"zh": "次重试...", "en": "retries..."},
    "invalid_port":          {"zh": "无效端口: {port}", "en": "Invalid port: {port}"},
    "machine_not_found_list": {"zh": "未找到机器: {machines}", "en": "Machine not found: {machines}"},
    "scp_failed_limit":      {"zh": "SCP 传输失败（带宽限制 {limit_kbs} KB/s）", "en": "SCP transfer failed (bandwidth limit {limit_kbs} KB/s)"},
    "rollback_failed":       {"zh": "回滚失败: {detail}", "en": "Rollback failed: {detail}"},
}


def t(key: str, **kwargs) -> str:
    """Translation function, returns text based on current language"""
    entry = _T.get(key)
    if not entry:
        return key
    text = entry.get(_lang, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
