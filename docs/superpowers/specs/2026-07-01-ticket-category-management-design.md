# 工单问题分类后台管理设计

## 背景与问题

当前系统中，工单创建页提供“一级分类”和“二级细分”两级选择器，数据源来自 `ticket_categories` 表。但该表目前仅通过 SQL 迁移脚本初始化数据，运行期没有管理入口。若数据库中缺少分类或需要调整，管理员无法自行维护，导致创建工单时无选项可选。

## 目标

为管理员提供问题分类的运行期维护能力：
- 新增一级分类和二级细分
- 编辑分类名称、排序、启用/禁用状态
- 删除未使用的分类
- 分类调整后，工单创建/列表/统计等页面自动生效

## 范围

- 后端：补全分类的创建、更新、删除接口
- 前端：新增分类管理后台页面，接入管理员菜单
- 数据模型复用现有 `ticket_categories`，不新增表

## 非目标

- 不支持超过两级的分类
- 不支持分类迁移（修改 parent_id 改变层级）
- 本期不做拖拽排序，仅通过 `sort_order` 数字调整

## 方案

采用“后台管理 CRUD”方案（方案 1）：新增 `/admin/categories` 页面，后端补全管理员接口，严格复用现有 users/groups/SLA 的管理后台模式。

## 数据模型

复用现有模型，不改动 schema：

```text
ticket_categories
- id: BIGSERIAL PK
- parent_id: FK -> ticket_categories.id, NULLABLE, CASCADE
- name: VARCHAR(100)
- level: SMALLINT CHECK(level IN (1, 2))
- sort_order: INT
- is_active: BOOLEAN DEFAULT TRUE
- created_at, updated_at
```

约束：
- 一级分类：`parent_id IS NULL AND level = 1`
- 二级分类：`parent_id IS NOT NULL AND level = 2`
- 二级分类的父级必须是一级分类

## 后端 API 设计

接口文件：`backend/app/api/v1/common.py`

### 1. 创建分类

```text
POST /api/v1/categories
Role: admin
```

请求体：

```json
{
  "name": "设备故障",
  "parent_id": null,
  "sort_order": 10
}
```

行为：
- `name` 必填，去重校验（同级下 name 唯一）
- `parent_id` 为空则创建一级分类，level=1
- `parent_id` 非空则必须是已存在的一级分类，level=2
- 返回 201 + `CategoryOut`

错误：
- 400：同级同名已存在
- 400：parent_id 指向二级分类或不存在

### 2. 更新分类

```text
PATCH /api/v1/categories/{id}
Role: admin
```

请求体：

```json
{
  "name": "硬件故障",
  "sort_order": 5,
  "is_active": true
}
```

行为：
- 允许修改 `name`、`sort_order`、`is_active`
- 禁止修改 `parent_id` 和 `level`
- 更新后 `updated_at` 自动刷新

错误：
- 404：分类不存在
- 400：同级同名已存在

### 3. 删除分类

```text
DELETE /api/v1/categories/{id}
Role: admin
```

行为：
- 物理删除
- 若该分类有关联工单（`tickets.category_id`），返回 400
- 若删除一级分类，其下二级分类应一并处理：
  - 方案 A（本期采用）：一级分类下若存在二级分类，禁止删除，提示先删除子分类
  - 方案 B（备选）：删除一级分类时级联删除其下所有二级分类（仅当均无工单关联）

错误：
- 404：分类不存在
- 400：分类下存在关联工单
- 400：一级分类下存在二级分类

### 4. 获取分类树（现有接口，行为不变）

```text
GET /api/v1/categories
```

返回激活状态的分类树，用于工单创建页等消费端。

## 前端设计

### 路由

```text
/admin/categories -> CategoriesView.vue
```

在 `frontend/src/router/index.ts` 的 admin 路由区新增。

### 菜单

在 `frontend/src/layouts/TheSidebar.vue` 的管理员区域新增“问题分类”菜单项，图标使用 `Folder` 或 `Collection`。

### 页面布局

`frontend/src/views/admin/CategoriesView.vue`：

- 顶部：标题“问题分类管理” + 新增分类按钮
- 主体：左侧一级分类列表（`el-table`），右侧二级分类列表
- 操作：
  - 点击一级分类，右侧显示其下二级分类
  - 每个分类行提供“编辑”和“删除”按钮
  - 新增/编辑通过 `el-dialog` + `el-form` 完成

### 表单字段

- 分类名称（必填）
- 父级分类（仅新增二级分类时选择，一级分类时隐藏）
- 排序号（数字，越小越靠前，默认 0）
- 启用状态（switch）

### API 模块

新增 `frontend/src/api/categories.ts`，封装：

```typescript
export const categoryApi = {
  list: () => ...,      // GET /categories?flat=true（如有需要）或复用 overviews.ts
  create: (data) => ..., // POST /categories
  update: (id, data) => ..., // PATCH /categories/{id}
  remove: (id) => ...,   // DELETE /categories/{id}
}
```

当前 `frontend/src/api/overviews.ts` 中的 `getCategories()` 仅返回树形结构用于选择器。分类管理页面需要扁平列表以便编辑，可考虑：
- 选项 A：复用 `getCategories()` 并在前端拍平
- 选项 B：新增 `GET /categories?flat=1` 参数

本期采用选项 A，减少后端改动。

## 权限

- 后端接口使用 `require_role("admin")` 保护
- 前端菜单和路由仅对 `authStore.isAdmin` 显示

## 错误处理

- 后端返回的业务错误统一使用 `HTTPException(status_code=400/404, detail="...")`
- 前端用 `ElMessage.error` 展示后端 `detail`
- 删除确认使用 `ElMessageBox.confirm`

## 联动影响

- 工单创建页 `TicketCreateView.vue` 在分类保存成功后刷新 `metaApi.getCategories()`，确保新分类立即可选
- 分类管理页面修改 `is_active` 后，创建页下次拉取时自动过滤掉禁用分类
- 仪表盘和报表中的 `by_category` 统计基于 `tickets.category_id`，历史数据不受影响

## 测试要点

- 创建一级分类成功，创建二级分类挂到该一级下成功
- 创建二级分类时 parent_id 指向二级分类失败
- 删除有工单的分类失败
- 删除一级分类时若存在二级分类失败
- 非 admin 用户访问管理接口返回 403
- 前端分类管理页面增删改后列表刷新

## 依赖

- 现有 `ticket_categories` 表和 `CategoryOut`/`CategoryCreate` schema
- 需要新增 `CategoryUpdate` schema（允许部分字段更新）
- 现有 `require_role` 权限依赖
- 现有 admin 页面模式（`GroupsView.vue` / `SLAView.vue`）
