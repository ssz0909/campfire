# Bing自动同步上线记录

- 上线日期：2026-11-17；功能提交：7d4027f6b55e8a36261cff282a9705e1e11d7858。
- 当前版本：/opt/campfire/releases/bing-20261117T114511Z。
- 原版本：/opt/campfire/releases/home-20261117T083156Z。
- 备份：/opt/campfire/backups/before-bing-20261117T114511Z，包含完整旧版本、数据库dump、Nginx配置及rollback.sh；回退前检查活跃任务。无数据库迁移。
- 基线259个源文件校验通过，仅覆盖两个后端和两个前端源文件及新构建资源，保留旧静态资源和既有凭据。
- 31项站长工具、GEO及浏览器回归通过；前端构建通过。切换前两次确认无活跃发布、视频生成及员工任务（沿用已记录历史孤立任务排除）。
- 上线检查：健康接口production/ok，systemd active，首页、llms、素材页SPA入口正常，线上主入口、管理后台及GEO统计资源与发布文件一致；Bing同步接口未登录返回401。
- Google既有凭据和自动同步设置保留；Bing尚未配置真实API Key，因此未执行真实账号的数据同步。管理员需填写后手动同步并检查结果。
