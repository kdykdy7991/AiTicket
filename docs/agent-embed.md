# 工单智能助手接入

“智能助手”入口默认只对管理员开放。管理员可在「用户管理 → 编辑用户 → 额外权限」
勾选「智能助手」，把入口授予其它角色的账号。该权限不改变账号的工单角色，也不会
提升其在 Debussy 侧的身份；只读观察员保持全局只读身份，不可使用此权限。

工单后端 `POST /api/v1/agent/embed/code` 根据当前登录会话获取用户 ID、姓名和角色，
使用该系统独有的 Client ID 和 Secret 向 Debussy
`POST /api/embed/v1/auth/exchange` 换取 60 秒有效的一次性 code。浏览器只收到
code 和发布页地址，再通过指定 Debussy Origin 的 `postMessage` 交给 iframe。
code 不进入 URL 或浏览器存储。离开页面或退出登录时清理 iframe。

## 配置

在仓库根目录的 `.env` 中设置（可从根目录 `.env.example` 创建）：

- `AGENT_EMBED_URL`：浏览器可访问的 Debussy 发布地址，含 `/embed/pub_...`。
- `AGENT_EMBED_API_URL`：**工单 API 进程可访问**的 Debussy 服务端基础地址。
  与浏览器地址可以不同；它不能指向仅监听宿主机回环地址、容器无法访问的服务。
- `AGENT_EMBED_CLIENT_ID` 和 `AGENT_EMBED_CLIENT_SECRET`：Debussy 为该受信任系统
  签发的专用凭据。Secret 仅放在工单后端环境变量中。

工单后端不再维护第二份页面来源白名单。浏览器 `Origin` 原样交给
Debussy，由发布应用及受信任系统的允许来源决定是否接受，并据此生成
iframe 的嵌入策略。换票接口要求当前用户是管理员，或持有「智能助手」额外权限。
只有管理员会在 Debussy 侧标识为 `admin`，其它账号统一为 `customer_service`。

开发 Compose 的 API 服务直接读取根目录 `.env`，因此无论从哪个目录调用
Compose，Embed 配置都会进入容器。修改配置后需重新创建 API：从仓库根目录执行
`docker compose --env-file .env -f backend/docker-compose.yml up -d --no-deps --force-recreate api`。
其他服务及 Compose 插值仍使用命令指定的 `--env-file`；推荐通过 `make backend`
启动完整开发环境。智能助手可选；未配置时 API 仍可启动，但访问助手会提示尚未完成配置。

当前发布应用的公开配置允许 `http://localhost:5173`、
`http://127.0.0.1:5173` 和 `http://10.113.114.88:5173`。实际允许来源
以 Debussy 发布应用的配置为准；协议、主机和端口共同决定 Origin。
其他开发地址需由平台侧先配置支持。

当前开发环境的浏览器 Embed 地址应配置为 `http://10.113.114.88:5176/embed/pub_...`，
不能使用 `127.0.0.1`，否则其他机器会连接到各自的本机。客户端需能访问 5176，
并使用已获平台授权的工单页面来源（例如 `http://10.113.114.88:5173`）。
其他主机名、端口或 HTTPS 来源仍需加入平台允许来源。

当前 Debussy Vite 监听 `0.0.0.0:5176`，公开 Embed 路径并将 `/api/embed` 代理到
只监听本机回环地址的 `127.0.0.1:8768`。工单 API 容器无法直接访问这两个地址，
开发 Compose 中的 `agent-bridge` 只转发换票接口。因此
`AGENT_EMBED_API_URL` 使用 `http://10.113.114.88:8767`。
如果 8768 进程无响应，换票会超时；应先恢复 Debussy 后端服务。

Embed 的用户身份只用于 Debussy 对话隔离。现有 MCP 工具仍按平台统一的
只读服务令牌授权，不自动继承客服的工单权限。
