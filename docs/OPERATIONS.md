# KnowledgeHub 运维手册

## 1. 当前安装状态

截至 2026-07-16，KnowledgeHub `0.1.0` 已完成开发并安装：

- CLI：`/Users/your-user/KnowledgeHub/.venv/bin/kb`
- 配置：`/Users/your-user/KnowledgeHub/config/knowledge-bases.yaml`
- 数据库：`/Users/your-user/KnowledgeHub/index/knowledge.db`
- 知识库：`daily-work` 5 个 roots，`business-dev` 29 个 roots
- 索引：850 个文档、16,610 个 chunks、0 个 parse errors
- Claude MCP：用户级 `knowledgehub`，已连接
- Codex MCP：全局 `knowledgehub`，已启用
- launchd：`com.example.knowledgehub.daily-scan`，已加载
- 调度：每天本地时间 12:00，`RunAtLoad=true`
- 最近真实任务：2026-07-16 11:39:09–11:39:12，成功；新增 2、更新 4、跳过敏感文件 60、失败 0
- Lark：真实摘要发送验证成功，outbox 为空

## 2. 初始化或重装运行时

```bash
cd /Users/your-user/KnowledgeHub
uv sync --python 3.12 --all-groups
.venv/bin/kb config validate --config config/knowledge-bases.yaml
.venv/bin/kb init --config config/knowledge-bases.yaml
```

`config/knowledge-bases.yaml` 是本机配置，不应提交凭据。配置示例位于 `config/knowledge-bases.example.yaml`。

## 3. 扫描与对账

### 3.1 Dry Run

Dry Run 会完成枚举、解析和变更判断，但不修改索引，也不发送 Lark：

```bash
/Users/your-user/KnowledgeHub/scripts/knowledgehub-daily-scan.sh --dry-run
```

### 3.2 正式每日流程

```bash
/Users/your-user/KnowledgeHub/scripts/knowledgehub-daily-scan.sh
```

脚本执行 `kb reconcile --all`，成功后写入当天标记并发送 Lark 摘要。当天已成功时再次运行会直接跳过；人工强制重跑使用：

```bash
/Users/your-user/KnowledgeHub/scripts/knowledgehub-daily-scan.sh --force
```

### 3.3 CLI 语义

`scan` 只处理本次枚举到的新增或修改文件，不做全局删除对账：

```bash
/Users/your-user/KnowledgeHub/.venv/bin/kb \
  scan --scope daily-work \
  --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

`reconcile` 对 Manifest 做完整对账，可识别删除/重命名，但仍只重建变化内容：

```bash
/Users/your-user/KnowledgeHub/.venv/bin/kb \
  reconcile --all \
  --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

### 3.4 单文件通知索引

专用 Skill 写入文档后可主动触发：

```bash
/Users/your-user/KnowledgeHub/.venv/bin/kb \
  notify /absolute/path/to/document.md \
  --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

## 4. launchd 安装

实际文件：

```text
/Users/your-user/Library/LaunchAgents/com.example.knowledgehub.daily-scan.plist
```

安装或更新：

```bash
cp \
  /Users/your-user/KnowledgeHub/deploy/com.example.knowledgehub.daily-scan.plist.example \
  /Users/your-user/Library/LaunchAgents/com.example.knowledgehub.daily-scan.plist

cp \
  /Users/your-user/KnowledgeHub/scripts/knowledgehub-daily-scan.sh.example \
  /Users/your-user/KnowledgeHub/scripts/knowledgehub-daily-scan.sh

chmod 755 /Users/your-user/KnowledgeHub/scripts/knowledgehub-daily-scan.sh
plutil -lint /Users/your-user/Library/LaunchAgents/com.example.knowledgehub.daily-scan.plist
zsh -n /Users/your-user/KnowledgeHub/scripts/knowledgehub-daily-scan.sh

launchctl bootout gui/$(id -u) \
  /Users/your-user/Library/LaunchAgents/com.example.knowledgehub.daily-scan.plist \
  2>/dev/null || true
launchctl bootstrap gui/$(id -u) \
  /Users/your-user/Library/LaunchAgents/com.example.knowledgehub.daily-scan.plist
```

验证：

```bash
launchctl print gui/$(id -u)/com.example.knowledgehub.daily-scan
```

预期包含：

```text
"Hour" => 12
"Minute" => 0
properties = runatload
```

`state = not running` 是正常空闲状态；重点检查 `last exit code = 0` 和 calendar trigger。

## 5. 当天去重、PID 锁和 stale lock

- 成功标记：`run/last-successful-daily-scan-date`
- 锁目录：`run/daily-scan.lock`
- PID 文件：`run/daily-scan.lock/pid`
- 默认 stale 阈值：6 小时

脚本只清理由无存活 PID 持有且达到 stale 条件的锁，避免并发扫描。不要直接删除仍有活跃 PID 的锁目录。

## 6. Lark 通知

复用现有脚本：

```text
/path/to/notification-script.sh
```

参数顺序是“正文、标题”：

```bash
/path/to/notification-script.sh \
  "这是一条 KnowledgeHub 通知测试。" \
  "KnowledgeHub 测试"
```

凭据由该脚本在项目目录外管理，禁止复制到 KnowledgeHub。通知失败会重试 3 次；索引成功不会因通知失败回滚，失败摘要写入 `logs/outbox/`。

## 7. Claude/Codex MCP

查看已安装配置：

```bash
claude mcp get knowledgehub
codex mcp get knowledgehub
```

服务命令：

```bash
/Users/your-user/KnowledgeHub/.venv/bin/kb \
  mcp --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

MCP 通过 stdio 工作，不应作为常驻网络端口启动。安装前已打开的 Claude/Codex 会话可能需要重启，才能重新加载工具清单。

## 8. 检索验收

```bash
# 健康状态
.venv/bin/kb status --json --config config/knowledge-bases.yaml

# 全文搜索
.venv/bin/kb search "KnowledgeHub" \
  --scope business-dev --limit 5 \
  --config config/knowledge-bases.yaml

# 项目路由
.venv/bin/kb project-context /Users/your-user/workspace/bit-news \
  --limit 5 --config config/knowledge-bases.yaml

# 读取命中原文
.venv/bin/kb read --document-id <document-id> --chunk-id <chunk-id> \
  --config config/knowledge-bases.yaml
```

## 9. 日志与报告

```bash
tail -100 /Users/your-user/KnowledgeHub/logs/daily-scan.out.log
tail -100 /Users/your-user/KnowledgeHub/logs/daily-scan.err.log
ls -lt /Users/your-user/KnowledgeHub/logs/reports | head
```

JSON 报告包含分库的 discovered/added/updated/deleted/unchanged/skipped/error 统计。敏感文件属于 `skipped`，不是解析失败。

## 10. 常见故障

| 现象 | 检查 |
|---|---|
| 12:00 没运行 | Mac 是否休眠、LaunchAgent 是否加载、日志和 `last exit code` |
| RunAtLoad 没重扫 | 当天成功标记会去重；需要重跑时使用 `--force` |
| 无 Lark 消息 | 通知脚本是否可执行、机器人是否在群中、`logs/outbox/` |
| 文档没有更新 | include/exclude、scope、文件 Hash、知识库是否 enabled |
| 搜索不到短中文词 | 1–2 字查询走 LIKE；确认内容未被敏感规则跳过 |
| 扫描卡住 | 检查锁 PID、超大文件、PDF/DOCX 解析；不要删除活跃锁 |
| 旧文档仍可搜索 | 使用 `reconcile` 而不是 `scan`，检查删除宽限与外键级联 |
| Claude/Codex 看不到工具 | `mcp get knowledgehub`，并重启安装前已打开的会话 |

## 11. 测试

```bash
cd /Users/your-user/KnowledgeHub
.venv/bin/pytest --cov=knowledgehub --cov-report=term-missing
```

2026-07-16 验收结果：8 passed，总覆盖率 75%，包含真实 stdio MCP 协议测试。

## 12. 备份与重建

配置和原文必须备份；索引可重建。备份 SQLite 时优先使用 SQLite 在线备份或先确认没有写任务。

```bash
cp -a config /absolute/backup/location/
cp index/knowledge.db /absolute/backup/location/
```

重建：

```bash
mv index/knowledge.db index/knowledge.db.backup.$(date '+%Y%m%d%H%M%S')
.venv/bin/kb init --config config/knowledge-bases.yaml
.venv/bin/kb reconcile --all --config config/knowledge-bases.yaml
```
