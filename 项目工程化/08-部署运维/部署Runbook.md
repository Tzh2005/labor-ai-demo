# 环境与部署 Runbook

> 本文是操作手册，不代表云端已经部署。执行云端章节前，必须完成 `07-发布上线/发布前检查清单.md` 并取得发布授权。

## 1. 运行前提

| 项目 | Windows 本地 | Ubuntu 22.04+ 云端建议 |
|---|---|---|
| Python | 3.10+ | 3.10+（用系统包或受管版本） |
| AI 运行时 | Ollama + `qwen2.5:3b` | Ollama + 经容量验证的模型 |
| 内存/磁盘 | 建议 8 GB / 10 GB 可用 | 首次演示建议至少 4 GB / 40 GB；生产按压测扩容 |
| 网络 | 仅本机回环 | SSH 管理、HTTPS 入口；Ollama 不暴露公网 |
| 数据 | 项目 `data/` | 受限目录、定时备份、最小权限 |

当前 `requirements.txt` 使用版本范围。正式生产上线前应在测试环境生成经过验证的锁定依赖清单；不要在事故期间临时升级所有依赖。

## 2. Windows 本地部署与验收

### 2.1 初次安装

```powershell
Set-Location D:\1-myFiles\Desktop\AI实习\labor-ai-demo
ollama pull qwen2.5:3b
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 不把密码写入代码、批处理文件或 Git
$env:DEMO_PASSWORD = "替换为随机长密码"
$env:OLLAMA_MODEL = "qwen2.5:3b"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
python check_environment.py --build-index
streamlit run app.py --server.port 8501
```

首次构建嵌入模型和 Chroma 索引需要网络、时间和磁盘。索引成功后，可在已有缓存环境设置 `HF_HUB_OFFLINE=1` 以减少联网检查。

### 2.2 冒烟验证

在另一 PowerShell 窗口执行：

```powershell
Invoke-WebRequest http://127.0.0.1:8501/_stcore/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing
python check_environment.py
```

随后在浏览器测试岗位检索、FAQ、来源展示、多轮追问和错误/信息不足的人工转接。不要只以“网页能打开”作为上线标准。

### 2.3 本地停止、重启和更新

- 前台运行的 Streamlit：在对应终端按 `Ctrl+C`。
- Ollama 未运行时：执行 `ollama serve`，或检查桌面应用后台服务。
- 更新前备份 `data/`，并记录当前 Git SHA；更新后的完整步骤按第 4 节执行。
- 端口冲突时先确认占用者：`Get-NetTCPConnection -LocalPort 8501`，不要盲目结束无关进程。

## 3. Ubuntu 云端部署（模板，未执行）

### 3.1 安全基线

1. 创建非 root 运行用户 `laborai`，为 SSH 管理员使用密钥登录。
2. 防火墙只开放 `22`（限制管理来源）、`80/443`（反向代理）；不要对公网开放 `11434` 或 `8501`。
3. 使用域名和 TLS；演示 IP 直连仅限短期、受控测试。
4. 将应用放入 `/opt/labor-ai-demo`，备份放入受限的 `/opt/backups/labor-ai-demo` 或独立对象存储。

示例初始化命令（管理员复核后执行）：

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx curl
sudo adduser --system --group --home /opt/labor-ai-demo laborai
sudo install -d -o laborai -g laborai -m 0750 /opt/labor-ai-demo /opt/backups/labor-ai-demo
```

按组织认可的方式安装 Ollama，并验证其仅监听本机；安装方式和版本必须记录在发布记录中：

```bash
sudo systemctl enable --now ollama
ollama pull qwen2.5:3b
curl --fail --max-time 5 http://127.0.0.1:11434/api/tags
```

### 3.2 获取经过验收的版本

优先从受控 Git 仓库的已签发标签或 CI 构建产物部署。示例使用标签，不在服务器上开发：

```bash
sudo -u laborai git clone <REPOSITORY_URL> /opt/labor-ai-demo
cd /opt/labor-ai-demo
sudo -u laborai git fetch --tags
sudo -u laborai git switch --detach vX.Y.Z
sudo -u laborai python3 -m venv venv
sudo -u laborai venv/bin/python -m pip install --upgrade pip
sudo -u laborai venv/bin/python -m pip install -r requirements.txt
sudo -u laborai venv/bin/python check_environment.py --build-index
```

发布包必须排除 `.env`、`venv/`、`data/*.db`、`chroma_db/`、缓存和日志。首次部署后，按受限迁移流程放入经过审核的 `data/jobs.json` 和 `data/faq.md`。

### 3.3 环境变量文件

创建 `/etc/labor-ai-demo.env`，仅 root 和服务账户可读：

```ini
DEMO_PASSWORD=替换为随机长密码
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_BASE_URL=http://127.0.0.1:11434
NO_PROXY=localhost,127.0.0.1
```

```bash
sudo chown root:laborai /etc/labor-ai-demo.env
sudo chmod 0640 /etc/labor-ai-demo.env
```

不要把该文件提交到 Git、贴进工单或通过普通聊天渠道发送。

### 3.4 Systemd 服务模板

创建 `/etc/systemd/system/labor-ai-demo.service`：

```ini
[Unit]
Description=Labor AI Demo Streamlit service
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=laborai
Group=laborai
WorkingDirectory=/opt/labor-ai-demo
EnvironmentFile=/etc/labor-ai-demo.env
ExecStart=/opt/labor-ai-demo/venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

启用、查看状态和日志：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now labor-ai-demo
sudo systemctl status labor-ai-demo --no-pager
sudo journalctl -u labor-ai-demo -n 100 --no-pager
curl --fail --max-time 5 http://127.0.0.1:8501/_stcore/health
```

### 3.5 Nginx 反向代理模板

仅在已配置 TLS 证书后启用公网入口。示例中的域名和证书路径必须替换；不要把 `8501` 直接暴露到公网。

```nginx
# /etc/nginx/sites-available/labor-ai-demo
# HTTP 只用于跳转，页面登录和会话始终经 HTTPS 传输。
server {
    listen 80;
    server_name ai.example.com;

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ai.example.com;

    ssl_certificate /etc/letsencrypt/live/ai.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000" always;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
        proxy_read_timeout 300;
    }
}
```

在防火墙中仅开放 `80`（仅跳转）、`443` 和受限来源的 `22`，绝不开放 `8501` 或 `11434`；确认已为域名签发证书后，执行 `sudo nginx -t` 再 reload。应继续配置访问日志轮转、请求体限制和组织所需的访问控制；这些配置未经真实域名环境验证前不能宣称生产就绪。

## 4. 标准升级步骤

1. 在目标环境执行备份并记录当前版本、磁盘空间和服务状态。
2. 获取目标标签/构建产物，核对版本和校验值。
3. 在维护窗口停止服务，替换应用文件，不覆盖 `data/`、`.env` 和备份目录。
4. 安装已批准的依赖；若数据变更，备份后再执行索引重建。
5. 启动服务，连续执行 3 次健康检查，再做关键路径冒烟。
6. 按发布流程观察；发生异常立即参照 `07-发布上线/回滚方案.md`。

## 5. 常见故障速查

| 现象 | 检查 | 优先处理 |
|---|---|---|
| 页面无法访问 | Streamlit 进程、8501 健康检查、Nginx 状态 | 读取日志后重启对应服务 |
| 问答报 Ollama 不可用 | `curl 127.0.0.1:11434/api/tags`、模型名 | 启动 Ollama 或拉取已批准模型 |
| 索引异常/结果陈旧 | `data/` 时间、`chroma_db/.data_signature` | 备份后重新构建索引 |
| SQLite locked/损坏 | 日志、磁盘、`PRAGMA integrity_check` | 停写、保留副本、从备份恢复 |
| 响应突然变慢 | CPU/内存、磁盘、并发、模型加载 | 限流/降级/回滚，勿直接删数据 |
| 认证失败 | 环境文件权限和值是否存在 | 仅由授权人轮换 `DEMO_PASSWORD` |
