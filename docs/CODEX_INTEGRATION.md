# Codex 接入 KnowledgeHub

## 1. 安装状态

KnowledgeHub 已作为全局 stdio MCP 注册到 Codex：

```text
名称：knowledgehub
命令：/Users/your-user/KnowledgeHub/.venv/bin/kb
参数：mcp --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
权限：只读
```

验证：

```bash
codex mcp get knowledgehub
codex mcp list
```

重新注册时使用：

```bash
codex mcp remove knowledgehub 2>/dev/null || true
codex mcp add knowledgehub -- \
  /Users/your-user/KnowledgeHub/.venv/bin/kb \
  mcp --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

## 2. MCP 工具

| 工具 | 作用 |
|---|---|
| `kb_project_context(project_path, limit)` | 把当前绝对路径路由到 `kb_id/project_id` 并返回项目文档 |
| `kb_search(query, scopes, project_id, limit)` | 在索引中检索并返回可追溯 chunk |
| `kb_read(document_id, chunk_id)` | 读取命中文档或指定 chunk 原文 |
| `kb_status()` | 返回索引健康、文档/chunk 数和最后扫描时间 |

MCP 不提供 `kb_write`、`kb_delete` 或原文件修改能力。

## 3. AGENTS.md 规则

本项目根目录已创建 `/Users/your-user/KnowledgeHub/AGENTS.md`。业务项目可复用其中规则：

1. 项目事实先调用 `kb_project_context`。
2. 搜索优先限制当前 `project_id` 或知识库 scope。
3. 用于结论的结果必须调用 `kb_read`。
4. 输出标题、绝对路径、章节路径和行号。
5. CodeGraph 负责代码符号/调用关系，KnowledgeHub 负责文档/历史事实。

## 4. 验证用例

```text
调用 kb_status，报告 KnowledgeHub 最后扫描时间、文档数和 chunk 数。
```

```text
先调用 kb_project_context 读取当前项目背景，再搜索当前有效 PRD 与架构决策。
```

```text
搜索“消息流控制”，对前 3 条重要命中调用 kb_read，并附绝对路径和行号。
```

## 5. 故障排查

```bash
codex mcp get knowledgehub
/Users/your-user/KnowledgeHub/.venv/bin/kb \
  status --json \
  --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

若 Codex 当前会话在安装前已启动，需新建或重启 Codex 会话，使 MCP 工具清单重新加载。
