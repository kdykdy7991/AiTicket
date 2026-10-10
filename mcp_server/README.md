# 工单只读 MCP Server

这个服务作为独立容器运行，对 Agent 平台提供 Streamable HTTP `POST/GET /mcp`。
当前暴露 `list_recent_tickets`、`filter_tickets`、`search_tickets`、
`get_ticket`、`list_categories` 五个查询工具。
平台的租户级令牌只代表 Agent 平台，不代表对话用户；因此本版不提供写工具。

## 配置

在项目根目录 `.env` 中设置两枚**不同**的随机令牌：

```env
MCP_BEARER_TOKEN=<给 Agent 平台保存的令牌>
MCP_INTERNAL_TOKEN=<MCP 容器调用内部 API 的令牌>
```

可用 `openssl rand -hex 32` 分别生成。生产部署执行
`docker compose -f docker-compose.prod.yml up -d --build`。
Web 容器将 `/mcp` 代理至 MCP 容器，平台连接地址为
`https://<系统域名>/mcp`，认证方式选 Bearer Token，填入
`MCP_BEARER_TOKEN`。平台测试连接并同步工具后，还需在 Agent 中手动允许所需工具。

`MCP_INTERNAL_TOKEN` 仅在容器内部传递给 API，不应填到 Agent 平台。
内部 API 只挂载五个 GET 端点，无法使用这枚令牌执行现有工单写接口。
MCP 容器不直接连接数据库，也不持有客服账号或管理员账号。

开发环境可运行 `docker compose -f backend/docker-compose.yml up -d api mcp`。
当前开发机监听 `10.113.114.88:8002`，同一内网中的 Agent 平台使用
`http://10.113.114.88:8002/mcp`。若开发机地址变化，需同步调整 Compose
端口绑定及项目根目录 `.env` 中的 `MCP_ALLOWED_HOSTS`。

当前服务使用 MCP Python SDK 1.30，支持的协议版本为 2024-11-05、
2025-03-26、2025-06-18、2025-11-25；平台客户端的实际兼容性应通过
“测试连接 / 同步工具”确认。
