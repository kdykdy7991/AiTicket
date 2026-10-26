# 工单智能助手接入

第一版只向管理员显示“智能助手”入口，后端换票接口也只允许管理员调用。
客服账号暂不能进入。测试完成后可同时调整前后端角色限制。

工单后端 `POST /api/v1/agent/embed/code` 根据当前登录会话获取用户 ID、姓名和角色，
使用该系统独有的 Client ID 和 Secret 向 Debussy
`POST /api/embed/v1/auth/exchange` 换取 60 秒有效的一次性 code。浏览器只收到
code 和发布页地址，再通过指定 Debussy Origin 的 `postMessage` 交给 iframe。
code 不进入 URL 或浏览器存储。离开页面或退出登录时清理 iframe。

## 配置

`.env` 中设置：

- `AGENT_EMBED_URL`：浏览器可访问的 Debussy 发布地址，含 `/embed/pub_...`。
- `AGENT_EMBED_API_URL`：**工单 API 进程可访问**的 Debussy 服务端基础地址。
  与浏览器地址可以不同；它不能指向仅监听宿主机回环地址、容器无法访问的服务。
- `AGENT_EMBED_CLIENT_ID` 和 `AGENT_EMBED_CLIENT_SECRET`：Debussy 为该受信任系统
  签发的专用凭据。Secret 仅放在工单后端环境变量中。

工单后端不再维护第二份页面来源白名单。浏览器 `Origin` 原样交给
Debussy，由发布应用及受信任系统的允许来源决定是否接受，并据此生成
iframe 的嵌入策略。当前用户仍须通过工单系统的管理员鉴权。

从仓库根目录启动开发后端时，使用 `make backend`（已显式加载根目录
`.env`）。直接调用 Compose 时需写成
`docker compose --env-file .env -f backend/docker-compose.yml up -d --no-deps --force-recreate api`；
省略 `--env-file` 会让本仓库的 Embed 地址和换票凭据以空值进入容器，
智能助手接口返回“尚未完成配置”。

当前发布应用的公开配置允许 `http://localhost:5173`、
`http://127.0.0.1:5173` 和 `http://10.113.114.88:5173`。实际允许来源
以 Debussy 发布应用的配置为准；协议、主机和端口共同决定 Origin。
其他开发地址需由平台侧先配置支持。

当前 Debussy Vite 监听 `127.0.0.1:5176`，并将 `/api/embed` 代理到
只监听本机回环地址的 `127.0.0.1:8768`。工单 API 容器无法直接访问这两个地址，
开发 Compose 中的 `agent-bridge` 只转发换票接口。因此
`AGENT_EMBED_API_URL` 使用 `http://10.113.114.88:8767`。
如果 8768 进程无响应，换票会超时；应先恢复 Debussy 后端服务。

Embed 的用户身份只用于 Debussy 对话隔离。现有 MCP 工具仍按平台统一的
只读服务令牌授权，不自动继承客服的工单权限。
