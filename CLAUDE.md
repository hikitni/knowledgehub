# CLAUDE.md

## KnowledgeHub

本地多知识库统一索引 + AI 检索基础设施。注册多个知识目录，维护 SQLite/FTS5 全文索引，通过只读 MCP 向 Claude Code / Codex 提供带绝对路径、章节、行号的检索能力。

## 项目信息

- **版本**：0.1.0
- **运行时**：Python 3.12 + uv
- **构建**：hatchling
- **项目路径**：`/Users/your-user/KnowledgeHub`
- **虚拟环境**：`.venv/`（uv 管理）
- **索引数据库**：`index/knowledge.db`（SQLite WAL + FTS5 trigram）
- **配置文件**：`config/knowledge-bases.yaml`
- **MCP 注册**：`claude mcp add -s user`（User scope, stdio 传输）

## 架构

```
cli.py          → CLI 入口（kb scan/reconcile/search/read/notify/status/mcp）
mcp_server.py   → MCP stdio 服务（4 tool: kb_search/kb_read/kb_project_context/kb_status）
service.py      → 查询层（FTS5 搜索 + LIKE 短词回退 + 项目路径路由）
indexer.py      → 写入层（增量检测 + manifest 对账 + 删除 grace period）
database.py     → SQLite 连接 + schema（5 表）
config.py       → YAML 配置加载/校验
models.py       → dataclass 模型（AppConfig/Chunk/RunReport 等）
parsers.py      → 多格式解析（md/txt/yaml/json/html/pdf/docx）
chunker.py      → Markdown 按标题分 chunk + 大块拆分 + overlap
security.py     → 路径拒绝 + 敏感内容正则检测
```

## 开发命令

```bash
# 安装依赖
uv sync --dev

# 运行测试
uv run pytest

# 校验配置
.venv/bin/kb config validate

# 增量扫描
.venv/bin/kb scan --all

# 全量对账（每日定时任务使用）
.venv/bin/kb reconcile --all

# 全文检索
.venv/bin/kb search “关键词” --scope daily-work

# 项目知识路由
.venv/bin/kb project-context /path/to/project

# 查看健康状态
.venv/bin/kb status --json

# 启动 MCP 服务（stdio）
.venv/bin/kb mcp
```

## 知识库配置

| ID | 名称 | 类型 | roots 数 |
|---|---|---|---|
| `daily-work` | 日常工作知识库 | document-vault | 5 |
| `business-dev` | 业务开发知识库 | project-collection | 28 |

## 数据模型

| 表 | 作用 |
|---|---|
| `knowledge_bases` | 知识库注册元信息 |
| `documents` | 文档 metadata（路径/hash/mtime/状态） |
| `chunks` | 分块内容（heading_path/行号/content_hash） |
| `chunks_fts` | FTS5 虚表（trigram tokenizer） |
| `scan_runs` | 扫描运行历史 |

## 核心机制

- **增量检测**：mtime_ns + size 快速跳过 → SHA-256 二次确认
- **中文搜索**：trigram tokenizer 天然支持；1-2 字查询走 LIKE 回退
- **安全边界**：路径拒绝（.env/私钥/证书） + 内容正则检测（密码/token/AWS key）
- **容错**：parse error 保留最后成功索引；删除有 grace period 防误删
- **调度**：macOS launchd 每日 12:00 执行 `kb reconcile --all`
- **通知**：飞书 Lark Bot Webhook 发送扫描摘要

## AI 接入方式

KnowledgeHub 通过 `claude mcp add knowledgehub -s user` 注册为用户级 MCP 服务：
- **命令**：`.venv/bin/kb mcp --config config/knowledge-bases.yaml`
- **传输**：stdio
- **scope**：User（所有项目可用）
- **移除**：`claude mcp remove knowledgehub -s user`

## 使用规则（面向 AI 消费者）

当任务涉及以下内容时，必须先查询 KnowledgeHub：

- 项目背景、业务规则和术语
- PRD、技术方案和架构决策
- 历史 Bug、故障和排障记录
- 接口契约、部署流程和运行手册
- 用户要求”之前””历史上””当前有效版本”

查询流程：

1. 调用 `kb_project_context`，参数使用当前项目绝对路径。
2. 调用 `kb_search` 搜索相关内容，优先限定返回的 `project_id`。
3. 对重要命中调用 `kb_read` 读取原文章节。
4. 回答必须标注文档标题、绝对路径、章节路径和行号范围。
5. 未检索到时明确说明，不得凭模型记忆编造项目事实。

代码符号、调用关系和影响范围继续使用 CodeGraph；KnowledgeHub 负责文档、业务背景和历史事实。飞书原文需先通过 已配置的企业连接器 抓取，落地本地后再由 KnowledgeHub 建索引。
