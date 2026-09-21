# 全通劳务本地招工助手

一个可离线运行的劳务派遣 AI 客服 Demo。岗位和 FAQ 保存在本地，回答由本地 Ollama 模型生成，不会把对话或数据上传到外部服务。

## 技术栈

| 组件 | 本项目中的作用 |
| --- | --- |
| Streamlit | 本地聊天和岗位浏览界面 |
| LangChain | RAG 提示词和模型调用链 |
| Ollama + qwen2.5 | 本地中文对话模型（默认 3b，可通过环境变量切换 7b） |
| BAAI/bge-large-zh-v1.5 | 中文语义嵌入模型 |
| ChromaDB | 本地持久化向量索引 |
| SQLite | 本地会话记录，便于演示后复盘 |

## 本地启动

前置条件：Windows、Python 3.10+、Ollama。建议使用 Python 3.11 或 3.12。

```powershell
cd D:\1-myFiles\Desktop\AI实习\labor-ai-demo
ollama pull qwen2.5:3b
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python check_environment.py --build-index
$env:DEMO_PASSWORD = "请设置一个足够长的随机密码"
streamlit run app.py
```

浏览器访问 `http://localhost:8501`。Windows 用户也可以在此目录双击 `一键部署脚本.bat`。

首次进行问答时，BGE 模型会下载并创建 `chroma_db/`。完成后，即使断网也能使用已下载的模型与索引。首次下载需要网络和约 2GB 可用磁盘空间。

## 功能

- 从 `data/jobs.json` 检索岗位，并在回答中显示检索来源。
- 从 `data/faq.md` 回答工资、住宿、入职与工作安排问题。
- 回答采用流式输出（逐字显示），页面显示首字与全文耗时。
- 聊天历史保留最近三轮，支持连续追问。
- 每条问答写入项目本地的 `data/labor_ai.db`，不会发送到外部服务。
- 页面内提供地区、岗位类型筛选，便于演示真实岗位信息。
- 索引记录数据签名；更新 `data/` 后，下次启动会自动重建 Chroma 索引。

## 企业开发流程

从产品需求到上线运维的第一版流程包位于 [`项目工程化/README.md`](项目工程化/README.md)，包含：

- 产品需求、用户故事、项目章程和迭代计划
- 信息架构、视觉规范、系统架构和安全边界
- RAG 检索演进方案（混合检索、重排序、路由、缓存、评估）
- 开发规范、分支/提交规范、测试策略和质量门禁
- 发布、回滚、部署 Runbook、监控、备份、事故响应和复盘

当前版本是本地优先 MVP。工程化文档会明确区分“已实现”“待验证”和“待开发”；历史演示文档中的准确率、成本、并发等数字需要以当前评估集和目标环境重新验证，不能直接视为生产承诺。

## 环境诊断

运行 `python check_environment.py --build-index` 可确认依赖、岗位数据、Ollama 服务、当前配置的对话模型，并创建 BGE + Chroma 索引。常见处理方式：

- Ollama 未连接：运行 `ollama serve`。
- 模型不存在：运行 `ollama pull 模型名`，或设置 `OLLAMA_MODEL` 为已安装的模型。
- 首次嵌入下载失败：恢复网络后重新提问，程序会继续创建本地缓存。
- 启动或提问卡顿数分钟：嵌入模型默认从本地缓存离线加载；如仍遇到长时间联网检查，可在启动前设置 `$env:HF_HUB_OFFLINE = "1"`。
- 提问时卡住或报 502：系统代理（Clash 等）开启时 httpx 会把本机请求也发往代理；程序已内置 `NO_PROXY` 修复，如仍异常可临时关闭系统代理。
- 要强制重建索引：删除项目目录下的 `chroma_db` 后重新启动应用。

## 配置

默认连接 `http://localhost:11434` 的 `qwen2.5:3b`（本地 CPU 响应更快）。如需切换模型，可在启动前设置：

```powershell
$env:OLLAMA_MODEL = "qwen2.5:7b"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:DEMO_PASSWORD = "请设置一个足够长的随机密码"
streamlit run app.py
```

实测对比（本机 CPU，1655 token 的 RAG 提问）：`3b` 首字约 10-15 秒、全文约 16-18 秒；`7b` 首字约 45 秒、全文约 52 秒。本地演示推荐 3b；上云后机器性能更强，可拉取 7b 并设置 `OLLAMA_MODEL=qwen2.5:7b` 获得更好效果。如需长期固定，可运行 `setx OLLAMA_MODEL qwen2.5:7b` 后重开终端；确认不再使用 7b 时可运行 `ollama rm qwen2.5:7b` 释放约 4.7GB 磁盘（随时可重新 pull 恢复）。
