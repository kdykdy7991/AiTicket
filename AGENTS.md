# 项目环境边界

- 本仓库是 `/home/hello/workspace/Skdy_Ticket_System`。本仓库的开发 Compose 项目是 `skdy-ticket-dev`，配置文件为 `backend/docker-compose.yml`。
- `skdy-poc` 容器属于 `/home/hello/workspace/Poc`，不是本仓库的服务或数据库。不要因其容器名、端口或运行状态将它称为本项目环境，也不要对它执行本项目的数据操作。
- 操作运行中的服务或数据库前，先用 `docker inspect` 核对容器的 `com.docker.compose.project.working_dir` 和 `com.docker.compose.project.config_files`。路径必须指向本仓库；否则停止该操作并说明目标未核实。
- 若用户只说“生效”而未给出环境，以当前仓库对应的已核实服务为目标。完成后明确报告实际操作的 Compose 项目、服务及验证结果，不推断用户正在访问的页面或其他环境的用途。
- 用户与部门成员关系通过用户管理界面和 API 修改；不要把日常增删成员写进基础数据播种。
