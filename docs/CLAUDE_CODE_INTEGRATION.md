# Claude Code 接入 KnowledgeHub

## 1. 安装状态

KnowledgeHub 已作为用户级 stdio MCP 注册到 Claude Code：

```text
名称：knowledgehub
Scope：User config
命令：/Users/your-user/KnowledgeHub/.venv/bin/kb
参数：mcp --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
权限：只读
```

验证：

```bash
claude mcp get knowledgehub
claude mcp list
```

重新注册时使用：

```bash
claude mcp remove knowledgehub -s user 2>/dev/null || true
claude mcp add --scope user knowledgehub -- \
  /Users/your-user/KnowledgeHub/.venv/bin/kb \
  mcp --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

## 2. MCP 工具

Claude 应看到：

```text
kb_search
kb_read
kb_project_context
kb_status
```

不提供写入、删除或覆盖原始知识文件的工具。

## 3. CLAUDE.md 规则

本项目根目录已创建 `/Users/your-user/KnowledgeHub/CLAUDE.md`。推荐业务项目复用以下流程：

1. 调用 `kb_project_context`，传入当前项目绝对路径。
2. 调用 `kb_search`，优先限定返回的 `project_id`。
3. 对支撑结论的命中调用 `kb_read`。
4. 回答附文档标题、绝对路径、章节路径和行号。
5. 未检索到时明确说明，不能凭模型记忆编造项目事实。

代码符号、调用关系和影响范围使用 CodeGraph；KnowledgeHub 负责文档、业务背景和历史事实。

## 4. 推荐问法

```text
基于 KnowledgeHub，说明 Phase2 V3 相对 V2 的变化，并附原文路径和行号。
```

```text
先读取当前项目背景，再查找关于半双工消息流控制的 PRD 和架构文档。
```

```text
调用 kb_status，告诉我最后扫描时间、文档数和 chunk 数。
```

## 5. 故障排查

```bash
claude mcp get knowledgehub
/Users/your-user/KnowledgeHub/.venv/bin/kb \
  status --json \
  --config /Users/your-user/KnowledgeHub/config/knowledge-bases.yaml
```

若 Claude Code 进程在安装前已启动，重新启动会话，使 MCP 工具列表重新加载。
