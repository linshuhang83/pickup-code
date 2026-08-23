# 取件码 — 快递取件码自动获取与提醒

自动读取 Mac 上 iMessage 同步的短信，解析菜鸟驿站、兔喜、丰巢、快宝等驿站的取件码，按驿站分组展示在网页上（Mac 浏览器 + iPhone PWA），新取件码到达时通过 Bark 推送到 iPhone 锁屏。

## 原理

所有驿站的取件码统一通过短信到达手机，iPhone 短信经 iMessage 同步到 Mac 的 `~/Library/Messages/chat.db`。本服务监控该数据库，新短信到达即解析入库。

```
iPhone 短信 ──iMessage 同步──> Mac chat.db
                                   │
                          Mac 后台服务 (Python)
                          ├─ sms_monitor  监控 chat.db（watchdog + 30s 轮询）
                          ├─ parser       正则提取 驿站名 + 取件码
                          ├─ database     SQLite 存储 + 去重
                          ├─ notifier     Bark 推送
                          └─ FastAPI      http://<Mac IP>:8787
                                   │
                     Mac 浏览器 / iPhone PWA（添加到主屏幕）
```

## 快速开始

```bash
./scripts/run.sh
```

1. 浏览器打开 `http://localhost:8787`
2. **首次运行需授权短信读取**（见下节）
3. iPhone 打开 `http://<Mac 局域网 IP>:8787` → Safari 分享 → 添加到主屏幕

> **环境要求**：Python ≥ 3.10（本服务使用 `X | None` 类型标注语法）。

## TCC 授权（首次必做，最关键一步）

macOS 隐私保护会拦截对 chat.db 的读取。服务日志出现 `无法打开短信数据库` 或 API 一直为空时，执行：

1. 打开 **系统设置 → 隐私与安全性 → 完全磁盘访问权限**
2. 点击 **+**，添加并勾选 **终端**（以及你用来启动服务的 App，如 VS Code）
3. 重启服务：`Ctrl+C` 后重新 `./scripts/run.sh`
4. 验证：`curl "http://localhost:8787/api/packages?status=pending"` 能看到短信解析出的记录

## 前提：iPhone 短信同步到 Mac

- Mac 上打开"信息"App，确认已登录 iMessage（`信息 → 设置 → iMessage 信息`）
- iPhone：`设置 → 信息 → 短信转发`，勾选你的 Mac
- 检查方式：`~/Library/Messages/chat.db` 存在且最近有新短信（服务日志无 `短信数据库不存在` 警告）

## 手机锁屏提醒（可选）

新取件码到达时，可以直接在 iPhone 锁屏上弹出提醒，不用打开网页也能第一时间看到。

1. iPhone 的 App Store 搜索并安装免费 App「[Bark](https://apps.apple.com/app/id1403753865)」
2. 打开 Bark，复制首页顶部网址的最后一段字母数字（如 `https://api.day.app/abcdef` 中的 `abcdef`）
3. 网页右上角 → 设置 → 粘贴到输入框 → 点「发一条测试提醒」验证

不想设置就留空，不影响网页使用。

## 使用说明

- **两个 Tab**：未取件（默认）/ 已取件（可撤销）
- **分组排序**：按驿站分组，组内按到达时间倒序；组间按该站最新包裹时间倒序
- **每页 10 条**，驿站跨页时组头在下一页重复显示
- **标记已取**：点"已取"按钮实时从未取列表移除；"已取件"Tab 可撤销
- **手动添加**：顶栏 + 按钮，填驿站名和取件码（拼多多等无码短信的补漏入口）
- **删除记录**：每条记录右侧"删除"按钮（需确认）。同一驿站同一天重复到达的相同取件码会自动合并显示，删除时一并删除
- **自动刷新**：页面 30 秒轮询 + 新短信实时监听

## 访问口令（可选）

默认**不启用**访问口令，网页打开即用（适合家庭内网）。如需加一道口令：

```bash
QJK_TOKEN=你的口令 ./scripts/run.sh
```

启用后，电脑和手机的浏览器打开网页都会提示"未授权"，需在网页 设置 → 访问口令 中填入相同口令。口令保存在各设备浏览器本地，之后自动带上。

> 提示：启用口令后，网页在请求数据收到"未授权"时会自动跳到设置页引导填写。

## 手机端（iPhone PWA）注意事项

- 添加到主屏幕后以独立窗口打开，体验与 App 一致
- **局限**：iOS 只允许 HTTPS 页面注册 Service Worker，局域网 HTTP 下无法启用离线缓存，页面每次打开都实时从 Mac 获取数据——正常使用不受影响，只是断网时打不开
- 若网络不佳加载缓慢，可下拉刷新或重开页面

## 已知限制

- **拼多多短信不含取件码**（只有运单号），无法自动解析——这类包裹的取件码由驿站另行发送（菜鸟等），收到即自动入库；确无短信时可手动添加
- **30 天窗口**：只处理最近 30 天的短信，更早的历史短信不导入
- **短信同步中断**：若 Mac 的 iMessage 长期未收到短信（服务日志显示扫描到 0 条新短信），检查上面"前提"一节
- 蜂窝网络（外出）时无法访问局域网网页，由 Bark 推送覆盖提醒场景

## 测试

```bash
.venv/bin/python -m pytest server/tests/
```

99 个测试覆盖：解析（含虚构化的多平台短信文案样本）、去重（含一条短信多取件码、手动/短信互不干扰）、分页分组排序、监控（游标恢复、混合时间刻度、回填不推送）、状态流转、API、鉴权、Bark 推送（mock 网络）。

## GitHub + Vercel 部署

本应用不能将完整后端运行在 Vercel：iMessage 数据库、SQLite 和短信监听必须保留在 Mac。部署架构为“Vercel 静态前端 + Tailscale Funnel + Mac FastAPI”。

### 1. 启动受保护的 Mac 后端

```bash
QJK_TOKEN='请使用高强度随机口令' ./scripts/run.sh
```

不要将真实口令写入仓库。Mac 必须保持开机，且该服务必须持续运行。

### 2. 启用 Tailscale Funnel

安装 Tailscale Standalone macOS 版本，登录后安装 CLI integration，然后执行：

```bash
tailscale funnel --bg 8787
tailscale funnel status
```

首次启用会打开 Funnel 授权页。它只应把 HTTPS 请求转发到 `http://127.0.0.1:8787`。

### 3. 导入 Vercel

1. 将仓库保持为 GitHub Private。
2. 在 Vercel 导入 GitHub 仓库。
3. 设置 `Root Directory = web`。
4. 设置 `Framework Preset = Other`。
5. 不设置 Build Command，`Output Directory = .`。
6. 部署后在网页“设置”中填入 Mac 后端使用的同一个访问口令。

### 故障排查

- 页面能打开但数据加载失败：检查 Mac 是否休眠、`scripts/run.sh` 是否运行。
- 本地能访问但 Vercel 不能：运行 `tailscale funnel status` 检查 Funnel。
- 返回 `401`：网页保存的访问口令与 Mac 启动口令不一致。
- Funnel 主机名变更：更新 `web/vercel.json` 中的 Rewrite origin 并重新部署。

## 技术栈

Python + FastAPI + SQLite + watchdog + 原生 JS + PWA + Bark。运行时不依赖任何外部服务（唯一的外网请求是启用 Bark 后的推送调用），网页无 CDN 依赖，可完全离线使用。
