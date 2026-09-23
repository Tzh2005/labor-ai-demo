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
| SQLite | 本地会话、岗位、候选人和报名记录，便于演示后复盘 |

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
- 回答会在完整安全检查后显示，并记录最近一次回答总耗时。
- 聊天历史保留最近三轮，支持连续追问。
- 每条问答写入项目本地的 `data/labor_ai.db`，不会发送到外部服务。
- 页面内提供地区、岗位类型筛选，便于演示真实岗位信息。
- “项目驾驶舱”展示岗位、报名、录用转化、交付风险和在岗快照；“人员派工”页支持候选人晋级为工人主档、派工和入场/离场状态时间线；“审计证据”页展示项目操作哈希链。
- “候选人与报名”页支持登记候选人、按岗位和技能生成可解释推荐，并创建报名记录、流转面试/录用状态。
- 本地演示可运行 `python demo_seed.py` 写入 5 名虚构测试工人、5 条报名、3 条派工和 3 条在岗快照；脚本幂等，测试数据姓名均带“测试工人·”前缀。
- 检索默认使用向量 + 词法的混合召回与 RRF 融合；设置 `RAG_RETRIEVAL_MODE=vector` 可回退到原向量检索。
- 索引记录数据签名；更新 `data/` 后，下次启动会自动重建 Chroma 索引。
- “项目知识库”支持为当前项目登记 UTF-8 的 `.txt` / `.md` 合同、SOP、入场要求和制度资料。原文仅保存在本机 `data/project_documents/`（不会提交到 Git），元数据、版本、SHA-256 校验和登记动作会写入 SQLite 与审计链。
- 项目问答会把当前项目资料与岗位/FAQ 分开检索，并在引用中标明资料类别、名称和版本。不同项目使用独立 Chroma 目录和集合，检索结果不会跨项目混用。

项目资料仅可用于脱敏演示或已获授权的业务资料。不要上传身份证、银行卡、工资/社保明细；PDF、Word、OCR、文档审批、正式权限模型、KMS 加密和生产级多租户仍属后续范围。

## 企业开发流程

从产品需求到上线运维的第一版流程包位于 [`项目工程化/README.md`](项目工程化/README.md)，包含：

- 产品需求、用户故事、项目章程和迭代计划
- 信息架构、视觉规范、系统架构和安全边界
- RAG 检索演进方案（混合检索、重排序、路由、缓存、评估）
- 开发规范、分支/提交规范、测试策略和质量门禁
- 发布、回滚、部署 Runbook、监控、备份、事故响应和复盘
- 开源借鉴与许可证边界：[`开源借鉴与合规边界.md`](项目工程化/04-技术架构/开源借鉴与合规边界.md)

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
# 可选：出现兼容性问题时临时回退到纯向量检索
$env:RAG_RETRIEVAL_MODE = "vector"
streamlit run app.py
```

实测对比（本机 CPU，1655 token 的 RAG 提问）：`3b` 首字约 10-15 秒、全文约 16-18 秒；`7b` 首字约 45 秒、全文约 52 秒。本地演示推荐 3b；上云后机器性能更强，可拉取 7b 并设置 `OLLAMA_MODEL=qwen2.5:7b` 获得更好效果。如需长期固定，可运行 `setx OLLAMA_MODEL qwen2.5:7b` 后重开终端；确认不再使用 7b 时可运行 `ollama rm qwen2.5:7b` 释放约 4.7GB 磁盘（随时可重新 pull 恢复）。
