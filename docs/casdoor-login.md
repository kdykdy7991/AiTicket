# Casdoor 登录

工单系统支持两种登录入口：工单登录页的用户名密码由后端通过 Casdoor 密码模式验证；“使用 Casdoor 登录”使用 OIDC 授权码 + PKCE。Casdoor Client Secret 仅存在工单 API 容器中。工单角色、所属组及启停状态仍由工单数据库决定；不会按同名账号自动关联。

## Casdoor 应用

在 `http://10.113.114.88:18000` 创建一个应用，例如“客服工单系统”，记录 Client ID 和 Client Secret。将实际使用的工单页面回调地址加入应用的 Redirect URL：

- `http://localhost:5173/auth/casdoor/callback`
- `http://127.0.0.1:5173/auth/casdoor/callback`
- `http://10.113.114.88:5173/auth/casdoor/callback`

## 工单配置

在项目根目录 `.env` 中设置 `CASDOOR_ISSUER=http://10.113.114.88:18000`、`CASDOOR_CLIENT_ID`、`CASDOOR_CLIENT_SECRET` 和允许的 `CASDOOR_REDIRECT_ORIGINS`。后者填来源，逗号分隔，不含回调路径。开发容器启动时需显式加载根目录 `.env`：

```bash
cd backend
docker compose --env-file ../.env -f docker-compose.yml build api
docker compose --env-file ../.env -f docker-compose.yml run --rm api alembic upgrade head
docker compose --env-file ../.env -f docker-compose.yml up -d --no-deps --force-recreate api
```

## 验证

1. 管理员先在 Casdoor 的 `skdy` 组织建立账号，再由后台把 Casdoor 用户 ID 写入对应工单用户的 `casdoor_subject`，并将 `casdoor_issuer` 设为当前发行者地址。用户无自助绑定入口。
2. 在工单登录页分别验证用户名密码登录和“使用 Casdoor 登录”。已绑定的工单用户应以原有角色进入。
3. 未绑定的 Casdoor 用户、被停用的工单用户应无法登录。工单 `admin` 的用户名密码入口仍使用本地密码。

`CASDOOR_CLIENT_ID` 和 `CASDOOR_CLIENT_SECRET` 未填写时，Casdoor 登录入口不会显示。
