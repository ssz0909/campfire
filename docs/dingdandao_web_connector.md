# 订单来了 Web 酒店连接器

## 已验证协议

2026-10-15 使用测试账号通过 `https://www.dingdandao.com` 登录并读取账号授权的两个门店。当前 Web PMS 的公开 JavaScript bundle 明确使用：

- 登录路径：`POST /v2/user/public/checkDevice/login`
- 密码使用 AES-128-CBC、PKCS7 传输；密码不落库。
- 普通请求使用 `reqBody`、毫秒 `timestamp`、`version=1` 的 MD5 签名，配合 `uid`、`token`、`notSign=notSign` 和 `deviceId`。
- 门店列表：`POST /v2/user/web/user/ntw/list`
- 切换门店：`POST /v2/user/user/changeNtw`
- 门店资料：`POST /v2/ntw/web/ntw/get`
- 房型/房间：`POST /v2/core/web/accom/roomType/room/list/auth`
- 专业版订单分页：`POST /v2/hm-b/pro/web/accom/order/getPage`
- 标准版订单分页：`POST /v2/hm-b/web/accom/order/getPage`
- 营业日报：`POST /v2/um-b/web/pro/report/biz/daily/stats`，按 `bizDate` 查询；返回房费收入、住宿非房费收入、营业收入总计、出售间夜数、入住率、ADR、RevPAR 等聚合指标。

测试门店返回了 705 条近 90 天订单，房型和房间列表可正常读取。营业日报返回的“房费收入”“入住率”等为平台的官方经营口径，系统应优先使用这些聚合指标。

## 数据与安全边界

- 登录后只让用户选择账号实际授权的门店；门店编号在服务端再次校验，并且一个门店不能绑定多个企业。
- 数据库只保存加密 Web 会话和所选门店 ID，不保存账号密码，也不向前端返回 token。
- 订单明细采用字段白名单，去掉住客姓名、电话、邮箱、员工姓名、备注等 PII；金额区分“订单/住宿金额”和“财务实收”。
- 同步只允许最近 90 天，分页重复、字段变更和会话失效会停止或标记任务，避免静默写入错误数据。
- Web 会话和开放平台 `authAccessToken` 是两套独立认证；不能互换。

## 未完成与后续

- 短信/设备验证需要真实账号在官网完成验证后重新提交验证码；自动绕过验证码不属于实现范围。
- 营业日报已核实接口和字段，下一步将其聚合结果持久化到专用日报表，用于 AI 经营分析；订单同步暂存订单和入住明细。
- 生产环境应配置明确的 `CREDENTIAL_ENCRYPTION_KEY`，并按平台条款和账号授权范围使用此 Web 连接器。
