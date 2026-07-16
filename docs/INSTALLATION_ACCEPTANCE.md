# KnowledgeHub 安装验收记录

- 验收日期：2026-07-16
- 项目版本：0.1.0
- 项目目录：`/Users/your-user/KnowledgeHub`
- 运行环境：macOS，Python 3.12.13，SQLite 3.51.0

## 1. 代码与测试

```bash
.venv/bin/pytest --cov=knowledgehub --cov-report=term-missing
```

结果：8 passed，总覆盖率 75%。测试覆盖增删改对账、中文检索、短词回退、scope 隔离、敏感内容跳过、最后成功索引保留、项目路由、CLI 配置、Markdown chunk 和 stdio MCP 协议。

## 2. 首次真实索引

首次全量 `reconcile --all` 成功：

- 新增：847
- 跳过：60
- 失败：0
- 耗时：8.56 秒

后续文档与安装说明更新也通过增量 reconcile 写入索引，证明变化文件可以被正确更新。

## 3. 检索与读取

已验证：

- `kb search "KnowledgeHub" --scope business-dev`
- `kb search "半双工消息流"`
- `kb read --document-id ... --chunk-id ...`
- `kb project-context /Users/your-user/workspace/bit-news`

返回结果包含 `kb_id`、`project_id`、document/chunk ID、绝对路径、标题、章节路径、行号、片段和 rank。

## 4. MCP 协议

使用 MCP Python SDK 通过 stdio 启动实际命令：

```text
/Users/your-user/KnowledgeHub/.venv/bin/kb mcp --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

初始化成功，工具清单严格为：

```text
kb_search
kb_read
kb_project_context
kb_status
```

`kb_status` 和 `kb_search` 均返回真实索引数据。

## 5. Claude 与 Codex

Claude Code：用户级 `knowledgehub` MCP，状态 Connected。

Codex：全局 `knowledgehub` MCP，状态 enabled。

两者使用同一个只读命令、配置和 SQLite 数据库。

## 6. Lark

2026-07-16 执行真实每日扫描脚本并发送摘要，通知脚本返回“发送成功”。通知 outbox 为空，过程中未复制或输出 Lark Webhook 凭据。

## 7. launchd

安装位置：

```text
/Users/your-user/Library/LaunchAgents/com.example.knowledgehub.daily-scan.plist
```

服务：

```text
com.example.knowledgehub.daily-scan
```

验收结果：

- plist lint：OK
- shell syntax：OK
- bootstrap：成功
- calendar trigger：Hour 12 / Minute 0
- RunAtLoad：true
- RunAtLoad 首次运行：exit code 0
- 当天成功标记生效：重复运行输出 already completed successfully

## 8. 最终结论

KnowledgeHub 已从设计阶段进入可运行状态。实际扫描、增量更新、删除对账、全文检索、原文读取、项目路由、Claude/Codex MCP、Lark 摘要和每天 12:00 launchd 调度均已完成安装与验证。
