# 本地个性化

公开站每天更新通用数据，本地偏好只负责决定哪些条目值得占用你的注意力。两层相互独立：公开证据和原始分不被覆盖，偏好与反馈不上传服务器。

## 导入方式

本地版通过 `127.0.0.1` 运行时，会自动读取不入 Git 的 `local/profile.json`。请使用 README 中带 `--bind 127.0.0.1` 的启动命令，避免把私有画像暴露给局域网。

公开 Pages 使用以下方式安装：

1. 复制 `scorer/profile.default.json` 为一个本地 JSON 文件，或只保留其中的 `attention` 对象。
2. 在页面右上角点击“导入本地偏好”，选择该文件。
3. 页面会把经过字段白名单、数量限制和权重限幅后的设置写入当前站点的 `localStorage`。

也可以使用 `#profile=<base64url-json>` 形式的一次性安装链接。页面读取后会立即清除地址栏中的片段；URL fragment 不会随 HTTP 请求发送到服务器。

## 可调字段

- `focus_keywords`：命中后提高本地分。
- `deprioritize_keywords`：命中后显著下沉。
- `source_weights`：按来源微调，范围会限制在 `-15..15`。
- `kind_weights`：分别调整 `need / shift / builder`，范围会限制在 `-15..15`。
- `now_thresholds / later_thresholds`：三类内容的本地阈值。
- `now_limit / later_limit`：每天最多占用多少注意力。
- `now_kind_limits / later_kind_limits`：防止单一内容类型垄断首页。

条目级“有价值 / 噪声 / 稍后”反馈优先级更高。导出的反馈只是供人工复盘；项目不会根据少量点击自动改写公共规则，以免反馈回路漂移。

## 隐私边界

- 本地偏好键：`need-radar-profile-v1`。
- 本地反馈键：`need-radar-feedback-v1`。
- 两者都只存在于当前浏览器、当前域名。
- 清理浏览器站点数据会一并清除；换设备或换浏览器需要重新导入。
