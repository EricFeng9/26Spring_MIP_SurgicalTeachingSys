# Java Auth Demo (PostgreSQL)

这是一个可给前端直接调用的 Java 简易认证服务，目前支持：

- 玩家注册
- 玩家登录
- 玩家登出

## 技术栈

- Java 17
- PostgreSQL 14+
- JDBC (`org.postgresql:postgresql`)

## 数据表

- `players`: 存储账号、盐值和密码哈希
- `sessions`: 存储登录会话 token 和登出状态

## 数据库配置

服务启动时从环境变量读取 PostgreSQL 连接参数：

- `DB_HOST` 默认 `127.0.0.1`
- `DB_PORT` 默认 `5432`
- `DB_NAME` 默认 `retinal_auth`
- `DB_USER` 默认 `postgres`
- `DB_PASSWORD` 默认 `postgres`

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

## API 列表

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`

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
```

## 核心入口

- `com.retinal.auth.AuthService`
  - `register(username, password)`
  - `login(username, password)`
  - `logout(token)`
