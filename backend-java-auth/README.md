# Java Backend Demo

这是一个可给前端直接调用的 Java 后端服务，当前支持：

- 玩家注册
- 玩家登录
- 玩家登出
- 触发 Python 评估并读取报告
- 提交玩家操作会话并落盘（JSON + 术后图可选）
- 通过 multipart/form-data 直接上传文件（推荐 Unity / 移动端）

## 技术栈

- Java 17
- PostgreSQL 14+
- JDBC (`org.postgresql:postgresql`)

## 数据表

- `retinal_app.players`: 存储账号、盐值和密码哈希
- `retinal_app.sessions`: 存储登录会话 token 和登出状态
- `retinal_app.levels`: 关卡基础信息
- `retinal_app.image_versions`: 关卡图片版本
- `retinal_app.play_sessions`: 游戏会话
- `retinal_app.action_events`: 玩家操作事件
- `retinal_app.score_reports`: 评分报告
- `retinal_app.session_submissions`: 提交会话与文件落盘记录

## 数据库配置

服务启动时从环境变量读取 PostgreSQL 连接参数：

- `DB_HOST` 默认 `127.0.0.1`
- `DB_PORT` 默认 `5432`
- `DB_NAME` 默认 `retinal_auth`
- `DB_USER` 默认 `testconnecter`
- `DB_PASSWORD` 默认 `12345678`

先在 PostgreSQL 创建数据库（一次即可）：

```sql
CREATE DATABASE retinal_auth;
```

示例（PowerShell）：

```powershell
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "5432"
$env:DB_NAME = "retinal_auth"
$env:DB_USER = "postgres"
$env:DB_PASSWORD = "your_password"
```

## 运行

```bash
mvn compile
mvn exec:java
```

服务默认启动在：

- `http://localhost:8080`

首次运行会自动创建所需数据表：`players`、`sessions`

当前业务表统一创建在 `retinal_app` schema 下。

## API 列表

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `POST /api/evaluation/run`
- `POST /api/session/submit`
- `POST /api/session/submit-upload`

### 1) 注册

请求：

```json
{
  "username": "player_01",
  "password": "123456"
}
```

返回：

```json
{
  "success": true,
  "message": "注册成功。"
}
```

### 2) 登录

请求：

```json
{
  "username": "player_01",
  "password": "123456"
}
```

返回：

```json
{
  "success": true,
  "message": "登录成功。",
  "token": "uuid-token"
}
```

### 3) 登出

请求：

```json
{
  "token": "uuid-token"
}
```

返回：

```json
{
  "success": true,
  "message": "登出成功。"
}
```

### 4) 触发评估并返回报告

推荐直接传 `sample_root`，后端会自动在目录中寻找一对 `_simgt.json` / `_simplayer.json` 文件，并调用 Python 评分脚本生成报告。

请求：

```json
{
  "sample_root": "C:\\Users\\16771\\Desktop\\多媒体\\Project\\26Spring_MIP_SurgicalTeachingSys\\evaluation\\test\\sample_data\\Temp770298_sample",
  "python_executable": "python"
}
```

也可以直接传完整路径：

```json
{
  "question_json_path": "C:\\...\\770298-3_after_single_R_reg_simgt.json",
  "player_json_path": "C:\\...\\770298-3_after_single_R_reg_simplayer.json",
  "config_json_path": "C:\\...\\evaluation\\docs\\config.json",
  "scoring_output_json_path": "C:\\...\\evaluation\\test\\output\\Temp770298_sample_output.json",
  "python_executable": "python"
}
```

返回值是 Python 评估脚本生成的报告 JSON，后端会直接原样返回给调用方。

### 5) 提交会话（JSON 请求体）（仅作保留）

适用于前端已拿到玩家 JSON 文本、术后图 Base64 的场景。

接口：`POST /api/session/submit`

请求（示例）：

```json
{
  "user_id": 1,
  "case_id": "sample",
  "player_json": "{\"session_id\":\"xxx\",\"actions\":[...]}",
  "question_json_path": "C:/.../770298-3_after_single_R_reg_simgt.json",
  "postop_image_base64": "iVBORw0KGgoAAA...",
  "postop_image_mime": "image/png"
}
```

说明：

- `player_json` 必须是字符串形式 JSON。
- 术后图可选。支持字段别名：
  - `postop_image_base64` / `player_image_base64` / `postop_image`
  - `postop_image_mime` / `player_image_mime`

返回（示例）：

```json
{
  "success": true,
  "session_id": "SESS_xxx",
  "report": { "total_score": 59.9 },
  "paths": {
    "player_json_path": ".../data/sessions/SESS_xxx/player_input.json",
    "player_image_path": ".../data/sessions/SESS_xxx/player_operation.png",
    "report_json_path": ".../data/sessions/SESS_xxx/report.json"
  }
}
```

### 6) 提交会话（文件上传，推荐）

适用于 Unity、手机端或网页文件上传场景，前端无需手动做 Base64 转换。

接口：`POST /api/session/submit-upload`

Content-Type：`multipart/form-data`

表单字段：

- `user_id`（必填）
- `case_id`（必填）
- `player_json_file`（可选，推荐）
- `player_json`（可选，与 `player_json_file` 二选一）
- `postop_image_file`（可选）
- `player_image_file`（可选，术后图别名）
- `question_json_path`（可选，联调常用）
- `project_root`（可选）
- `python_executable`（可选）

校验规则：

- `user_id`、`case_id` 必填。
- `player_json_file` 或 `player_json` 至少提供一个。

## 前端调用示例 (fetch)

```javascript
const baseUrl = "http://localhost:8080";

async function register(username, password) {
  const resp = await fetch(`${baseUrl}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
  return await resp.json();
}

async function login(username, password) {
  const resp = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
  return await resp.json();
}

async function logout(token) {
  const resp = await fetch(`${baseUrl}/api/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  });
  return await resp.json();
}

async function runEvaluation(sampleRoot) {
  const resp = await fetch(`${baseUrl}/api/evaluation/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample_root: sampleRoot, python_executable: "python" })
  });
  return await resp.json();
}

async function submitSessionJson(payload) {
  const resp = await fetch(`${baseUrl}/api/session/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return await resp.json();
}

async function submitSessionUpload(formData) {
  const resp = await fetch(`${baseUrl}/api/session/submit-upload`, {
    method: "POST",
    body: formData
  });
  return await resp.json();
}
```

## 核心入口

- `com.retinal.auth.AuthService`
  - `register(username, password)`
  - `login(username, password)`
  - `logout(token)`
- `com.retinal.auth.EvaluationService`
  - `run(request)`
- `com.retinal.auth.SubmissionService`
  - `submit(request)`
  - `submitUploaded(request)`
