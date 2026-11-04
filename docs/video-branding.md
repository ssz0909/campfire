# 视频品牌片头

企业设置 → 视频品牌片头，可启用并保存名称（最多32字符）与展示时长（1–8秒，默认3秒）。
配置保存在本企业 `business_goals.video_branding`，其他企业不会继承。未配置的企业默认关闭。

片头为白色文字字标，配半透明深色底，结束前0.35秒淡出。可设置：
- 字体：默认中文字体、黑体、宋体；下拉框仅显示服务器已安装字体。
- 字号：画面宽度的2%–15%，默认6.2%；横屏同时限制相对画面高度，长名称自动缩小适配。
- 位置：左上、上中、右上、左中、正中、右中、左下、下中、右下。
- 左右/上下边距：各0%–30%，按整个文字底框到画面边缘的距离计算。居中方向保持居中，边距仍限制最大可用空间。
- 实时预览：使用服务端实际字体和相同排版函数，支持9:16、16:9、1:1画幅，无模型调用费用。

旧配置缺少新字段时自动使用默认字体、6.2%字号、上方居中、左右8%/上下14%边距，保持原排版；已有品牌名称和展示时长不会改变。
它叠加在原画面上，不插入额外片段，不改变视频时长；横屏、竖屏、方形画幅按安全边距自适应。
这是文字字标，当前不支持上传图形商标，且不会添加注册商标符号。

单镜头、多镜头、数字员工自动制作和失败后重新执行均在最终合成后统一处理，再生成预览缩略图，最后进入审核或自动执行流程。
使用模型原始片段合成，不将已加字标的成片再次作为输入；重复恢复不会重复叠加。
片头不调用大模型，不产生额外模型费用。已完成视频不自动重做；已有成片换配乐时通过视频流复制保留片头。
配置以最终合成时的企业设置为准；合成完成的素材将实际设置记录在 `asset_metadata.opening_brand`。

服务需要 FFmpeg、Pillow 及中文字体。Linux 自动查找 Noto Sans CJK 或文泉驿正黑，macOS 查找苹方；
特殊环境可在 `.env` 配置 `VIDEO_BRAND_FONT_PATH` 指定支持中文的字体绝对路径。
启用时缺少字体会提示配置错误；合成失败时停止成片流程，不会发布未加字标的结果。

接口：`PUT /api/v1/companies/{company_id}/video-branding`，需要本企业 `COMPANY_EDIT` 权限。

```json
{"enabled": true, "text": "安吉雲中溪", "duration_seconds": 1, "font": "serif", "font_size_percent": 6.2, "position": "bottom_right", "margin_x_percent": 8, "margin_y_percent": 14}
```

验证：`pytest tests/test_video_branding.py tests/test_video_relay.py tests/test_video_director.py`，
以及 `python frontend/tests/video-branding-ui.py`（构建前端后运行，本地模拟接口，不访问平台或生成视频）。

字体选项：`GET /api/v1/companies/{company_id}/video-branding/fonts`。
只读预览：`POST /api/v1/companies/{company_id}/video-branding/preview?aspect=9:16`，请求体与保存相同，返回透明PNG的base64；需本企业`COMPANY_VIEW`权限，不写入设置。
Linux可安装`fonts-noto-cjk`提供黑体、宋体。默认字体保留文泉驿优先以兼容原有线上排版；`.env`中的`VIDEO_BRAND_FONT_PATH`仍只覆盖“默认”选项。
