# 营火AI部署

品牌：营火AI · AI运营平台。宣传语：Always on, Always Growing。

服务器：129.211.64.132；站点：https://campfire.dawoai.com。

- 源码与前端产物：`/opt/campfire/releases/20261026`，`/opt/campfire/current` 指向当前版本。
- Python 3.11：`/opt/campfire/python`；虚拟环境：`/opt/campfire/venv`。
- 后端配置：`/opt/campfire/shared/.env`（权限 600），后端目录使用符号链接。
- 本地存储：`/opt/campfire/shared/storage`；浏览器：`/opt/campfire/shared/browsers`。
- 运行账号与服务：`campfire`；systemd 单进程监听 `127.0.0.1:8018`，避免进程内浏览器会话分散。
- Nginx：`/etc/nginx/conf.d/campfire.conf`，HTTPS 同源代理 `/api/`、`/files/`、`/health`，其他路径使用 SPA 回退。
- 证书由服务器 acme.sh 管理，安装至 `/etc/nginx/ssl/campfire.dawoai.com/`，续期后重载 Nginx。

参考模板见 `deploy/`。服务启动前先准备配置与数据库，并执行 `alembic upgrade head`。完整安装依赖使用 `uv pip install --python /opt/campfire/venv/bin/python .`，项目依赖来自 `backend/pyproject.toml`，不是不存在的 requirements.txt。

检查：`systemctl status campfire`、`journalctl -u campfire -n 100`、`curl https://campfire.dawoai.com/health`。重启：`systemctl restart campfire`。

生产 `PUBLIC_BASE_URL` 必须是实际公网 HTTPS 后端地址，使视频模型能读取带签名的参考图；禁止将上传目录公开成无鉴权静态目录。

远程服务器不显示用户本机 Chrome 窗口。平台发布页现提供公司权限隔离的云端登录画面，每 4 秒更新，支持扫码、点击、输入、拖动和刷新。截图接口禁止缓存；不返回 Cookie 或任意导航接口。收起画面不会关闭会话。必须由用户完成扫码，不能将浏览器启动当成已授权，平台登录及实际发布仍需真实账号验收。

已迁移原有账户、酒店、任务、视频项目、上传素材和模型/连接器配置，保留原密码及加密密钥。浏览器登录会话目录未迁移，平台需要重新授权。Chromium 已安装，并以 campfire 服务账号验证无界面启动成功；这仅验证浏览器运行依赖，不代表平台已登录或发布已验收。

备份时同时保存 PostgreSQL campfire 数据库、shared/storage、shared/.env 和 shared/secrets；配置与备份含敏感信息，只允许管理员读取，勿提交到代码仓库。恢复时必须保留原加密密钥。
