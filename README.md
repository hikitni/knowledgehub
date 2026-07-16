# KnowledgeHub

KnowledgeHub 是面向本地多知识库的统一扫描、增量索引和 AI 检索基础设施。

它不搬运原始文件，而是注册多个知识目录，检测新增、修改和删除，更新本地 SQLite/FTS5 全文索引，并通过只读 MCP 同时向 Claude Code 和 Codex 提供带绝对路径、章节、行号和原文片段的检索能力。

## 当前状态

- 实现版本：`0.1.0`
- 运行时：Python `3.12`
- 项目目录：`/Users/your-user/KnowledgeHub`
- 实际配置：`config/knowledge-bases.yaml`
- 索引数据库：`index/knowledge.db`
- 已启用知识库：`daily-work`、`business-dev`
- 首次真实索引：2026-07-16，共 850 个文档、16,610 个 chunks
- AI 接入：Claude Code 与 Codex 均已注册用户级/全局 `knowledgehub` MCP
- 调度：macOS launchd 每天本地时间 12:00 执行 `kb reconcile --all`
- 通知：复用本机 Lark 机器人脚本发送任务摘要

## 已实现能力

- 多知识库、多根目录和 `project_id` 路由
- Markdown、Text、YAML、JSON、HTML、PDF、DOCX 解析
- SHA-256 增量检测与 Manifest 全量对账
- SQLite WAL + FTS5 trigram 全文检索
- 1–2 字中文查询 LIKE 回退
- 显式 `chunk_id` 关联、scope/project 过滤
- 解析失败保留最后一次成功索引
- 敏感路径和敏感内容拒绝索引
- 只读 MCP：`kb_search`、`kb_read`、`kb_project_context`、`kb_status`
- PID 锁、stale lock 恢复、当天成功去重、Lark 重试与 outbox

## 快速使用

```bash
cd /Users/your-user/KnowledgeHub

# 校验配置
.venv/bin/kb config validate --config config/knowledge-bases.yaml

# 快速增量扫描：不做全局删除对账
.venv/bin/kb scan --scope daily-work --config config/knowledge-bases.yaml

# 完整 Manifest 对账：每日任务使用此命令
.venv/bin/kb reconcile --all --config config/knowledge-bases.yaml

# 全文检索
.venv/bin/kb search "半双工消息流" --scope daily-work --config config/knowledge-bases.yaml

# 项目知识路由
.venv/bin/kb project-context /Users/your-user/workspace/bit-news \
  --config config/knowledge-bases.yaml

# 查看健康状态
.venv/bin/kb status --json --config config/knowledge-bases.yaml
```

## 文档导航

| 文档 | 说明 |
|---|---|
| [完整技术实现方案](docs/TECHNICAL_IMPLEMENTATION.md) | 总体架构、数据模型、检测、索引、调度、安全与测试 |
| [Claude Code 接入](docs/CLAUDE_CODE_INTEGRATION.md) | 已安装 MCP、项目指令、检索流程与验证 |
| [Codex 接入](docs/CODEX_INTEGRATION.md) | 已安装 MCP、AGENTS.md 规则与验证 |
| [运维手册](docs/OPERATIONS.md) | 手动扫描、launchd、日志、Lark、备份与恢复 |
| [安装验收记录](docs/INSTALLATION_ACCEPTANCE.md) | 真实索引、MCP、Lark、launchd 和测试验收结果 |
| [知识库配置示例](config/knowledge-bases.example.yaml) | 多知识库、包含/排除规则、调度和通知配置 |

## 项目结构

```text
/Users/your-user/KnowledgeHub/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── src/knowledgehub/
├── tests/
├── config/
│   ├── knowledge-bases.example.yaml
│   └── knowledge-bases.yaml          # 本机实际配置，不提交凭据
├── docs/
├── deploy/
├── scripts/
├── index/                            # SQLite 索引
├── run/                              # PID、锁和当天成功标记
└── logs/                             # 扫描日志、JSON 报告和通知 outbox
```

## 安全边界

- Indexer 不修改、不删除、不移动原始知识文件。
- MCP 只提供读取和检索，不提供写入/删除工具。
- `.env`、私钥、证书、Token、凭据文件默认拒绝索引。
- Lark Webhook 或应用凭据保留在项目目录外，不复制进 KnowledgeHub。
