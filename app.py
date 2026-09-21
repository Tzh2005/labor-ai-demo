"""Streamlit workbench for the local labor-recruitment assistant."""

from __future__ import annotations

import html as html_module
import hmac
import logging
import os
import time
import uuid
from pathlib import Path

import streamlit as st

from ai_service import AIService, check_ollama, resolve_model_name
from conversation_store import ConversationStore
from knowledge_base import KnowledgeBase, load_jobs_file


logger = logging.getLogger(__name__)

# 每会话每分钟最多提问次数（防止 CPU 推理被滥用）
_MAX_QUESTIONS_PER_MINUTE = 10
# 限制写入 SQLite 和发送给模型的单次输入大小，避免滥用本地推理资源。
_MAX_QUESTION_LENGTH = 500


st.set_page_config(page_title="全通劳务招工助手", page_icon="AI", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
    :root { --ink: #183236; --jade: #087f73; --deep: #10383a; --mist: #edf6f3; --sun: #f4c95d; --coral: #ef8f6b; --line: #d5e4df; --paper: #f7fbf9; --muted: #607672; }
    .stApp { background: var(--paper); color: var(--ink); }
    .block-container { max-width: 1280px; padding-top: 1.2rem; padding-bottom: 2.4rem; }
    [data-testid="stSidebar"] { background: var(--deep); border-right: 0; }
    [data-testid="stSidebar"] * { color: #eef8f5 !important; }
    [data-testid="stSidebar"] .stButton > button, [data-testid="stSidebar"] .stButton > button * { color: var(--deep) !important; background: #f2faf7; border: 0; }
    [data-testid="stSidebar"] .stButton > button:hover { background: var(--sun); }
    [data-testid="stSidebar"] input { color: var(--deep) !important; background: #f2faf7 !important; }
    [data-testid="stSidebar"] input::placeholder { color: #59736d !important; }
    [data-testid="stSidebar"] hr { border-color: rgba(238, 248, 245, 0.18); }
    .brand-lockup { padding: 0.4rem 0 1.15rem; border-bottom: 1px solid rgba(238, 248, 245, 0.16); margin-bottom: 1.15rem; }
    .brand-kicker { color: #8ed8cb; font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase; font-weight: 700; }
    .brand-name { color: #ffffff; font-size: 1.2rem; font-weight: 760; margin-top: 0.25rem; }
    .brand-note { color: #b7d6d0; font-size: 0.78rem; margin-top: 0.12rem; }
    .hero { display: flex; align-items: stretch; justify-content: space-between; gap: 1.5rem; background: var(--deep); color: #ffffff; padding: 1.6rem 1.7rem; margin: 0.2rem 0 1.05rem; border-radius: 10px; overflow: hidden; }
    .hero-copy { max-width: 670px; }
    .hero-eyebrow { color: #8ed8cb; font-size: 0.74rem; letter-spacing: 0.12em; text-transform: uppercase; font-weight: 760; }
    .hero h1 { margin: 0.35rem 0 0; color: #ffffff; font-size: clamp(1.85rem, 3vw, 2.7rem); line-height: 1.12; letter-spacing: 0; }
    .hero p { margin: 0.55rem 0 0; color: #c5dfd9; font-size: 0.98rem; max-width: 580px; }
    .hero-visual { min-width: 220px; align-self: stretch; display: flex; align-items: center; justify-content: center; }
    .signal-board { position: relative; width: 210px; height: 108px; border: 1px solid rgba(142, 216, 203, 0.38); border-radius: 8px; background: rgba(255,255,255,0.05); padding: 1rem; }
    .signal-board::before, .signal-board::after { content: ""; position: absolute; left: 1rem; right: 1rem; height: 1px; background: rgba(142, 216, 203, 0.22); }
    .signal-board::before { top: 2.2rem; } .signal-board::after { top: 4.4rem; }
    .signal-bars { height: 100%; display: flex; align-items: flex-end; gap: 0.42rem; }
    .signal-bars i { display: block; width: 0.62rem; background: var(--sun); border-radius: 3px 3px 0 0; }
    .signal-bars i:nth-child(1) { height: 34%; } .signal-bars i:nth-child(2) { height: 62%; background: #8ed8cb; } .signal-bars i:nth-child(3) { height: 48%; } .signal-bars i:nth-child(4) { height: 80%; background: var(--coral); } .signal-bars i:nth-child(5) { height: 56%; background: #8ed8cb; }
    .metric-card { border: 1px solid var(--line); border-radius: 8px; background: #ffffff; padding: 0.85rem 1rem 0.72rem; min-height: 84px; }
    .metric-label { color: var(--muted); font-size: 0.72rem; margin-bottom: 0.18rem; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 720; }
    .metric-value { color: var(--ink); font-size: 1.3rem; font-weight: 760; }
    .metric-rule { height: 3px; background: var(--sun); margin-top: 0.5rem; border-radius: 2px; }
    .welcome-strip { display: flex; gap: 0.65rem; align-items: center; border: 1px solid var(--line); background: var(--mist); padding: 0.75rem 1rem; border-radius: 8px; margin: 0.85rem 0 0.95rem; color: var(--ink); }
    .welcome-dot { width: 9px; height: 9px; background: var(--jade); border-radius: 50%; flex: 0 0 auto; }
    .welcome-strip strong { font-size: 0.9rem; } .welcome-strip span { color: var(--muted); font-size: 0.82rem; }
    .workflow-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.7rem; margin: 0 0 1rem; }
    .workflow-item { display: flex; gap: 0.7rem; align-items: flex-start; padding: 0.8rem 0.9rem; border-top: 2px solid var(--line); background: #ffffff; }
    .workflow-index { color: var(--jade); font-size: 0.72rem; font-weight: 800; letter-spacing: 0.08em; }
    .workflow-item strong { display: block; color: var(--ink); font-size: 0.86rem; }
    .workflow-item span { display: block; color: var(--muted); font-size: 0.76rem; margin-top: 0.15rem; line-height: 1.35; }
    .auth-shell { max-width: 760px; margin: 8vh auto 0; background: #ffffff; border: 1px solid var(--line); border-radius: 10px; padding: 2rem 2.2rem; }
    .auth-kicker { color: var(--jade); font-size: 0.74rem; letter-spacing: 0.12em; text-transform: uppercase; font-weight: 760; }
    .auth-shell h1 { margin: 0.35rem 0 0; color: var(--ink); font-size: 2rem; }
    .auth-shell p { color: var(--muted); margin: 0.4rem 0 1.2rem; }
    .job-card { border: 1px solid var(--line); border-radius: 8px; background: white; padding: 1rem 1.05rem; margin-bottom: 0.7rem; }
    .job-card h3 { margin: 0; font-size: 1.05rem; color: var(--ink); }
    .job-meta { color: var(--muted); margin-top: 0.25rem; font-size: 0.9rem; }
    .job-salary { color: var(--jade); font-size: 1.05rem; font-weight: 700; margin: 0.55rem 0; }
    .status-ready { color: var(--jade); font-weight: 650; }
    .status-wait { color: #9b6500; font-weight: 650; }
    div[data-testid="stChatMessage"] { border: 1px solid var(--line); border-radius: 8px; margin-bottom: 0.6rem; color: var(--ink) !important; background: #ffffff; }
    div[data-testid="stChatMessage"] * { color: var(--ink) !important; }
    div[data-testid="stChatMessage"][data-testid*="user"] { background: #e8f3ee; }
    [data-testid="stChatInput"] textarea, [data-testid="stChatInput"] textarea::placeholder { color: var(--ink) !important; opacity: 1; }
    [data-testid="stChatInput"] { background: #ffffff; border: 1px solid var(--line); border-radius: 8px; }
    .stMarkdown, .stMarkdown p, [data-testid="stCaptionContainer"] { color: var(--ink); }
    @media (max-width: 700px) { .block-container { padding-left: 1rem; padding-right: 1rem; } .hero { padding: 1.2rem; } .hero-visual { display: none; } .hero h1 { font-size: 1.7rem; } .auth-shell { margin: 3vh 0 0; padding: 1.4rem; } .workflow-grid { grid-template-columns: 1fr; } }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner=False, ttl=3600)
def get_service() -> AIService:
    return AIService()


@st.cache_resource(show_spinner=False, ttl=3600)
def get_store() -> ConversationStore:
    return ConversationStore()


@st.cache_data(show_spinner=False)
def get_jobs() -> list[dict[str, object]]:
    return load_jobs_file(Path(__file__).resolve().parent / "data" / "jobs.json")


def initial_messages() -> list[dict[str, object]]:
    return [{
        "role": "assistant",
        "content": "您好，我是小通。我会根据本地岗位库和常见问题为您查找信息。您可以问工资、住宿、地点或入职要求。",
        "sources": [],
    }]


def history_text(messages: list[dict[str, object]]) -> str:
    recent = messages[-6:]
    return "\n".join(f"{'工人' if item['role'] == 'user' else '小通'}：{item['content']}" for item in recent)


def render_job(job: dict[str, object]) -> None:
    # 对所有用户可控字段做 HTML 转义，防止 XSS
    safe = {k: html_module.escape(str(v)) for k, v in job.items()}
    st.markdown(
        f"""
        <div class="job-card">
          <h3>{safe['factory_name']} · {safe['position']}</h3>
          <div class="job-meta">{safe['location']} · {safe['work_time']}</div>
          <div class="job-salary">{safe['salary']}</div>
          <div class="job-meta">要求：{safe['requirements']}</div>
          <div class="job-meta">福利：{safe['benefits']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


if "messages" not in st.session_state:
    st.session_state.messages = initial_messages()
if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "question_timestamps" not in st.session_state:
    st.session_state.question_timestamps: list[float] = []

# 密码只允许通过环境变量配置，避免将可公开访问的凭据写入源码。
configured_password = os.getenv("DEMO_PASSWORD")
if not configured_password:
    st.error("服务尚未配置访问密码，请由管理员设置 DEMO_PASSWORD 后重启。")
    st.stop()

# 密码认证（上云时必须保留；本地演示可注释掉）
if not st.session_state.authenticated:
    with st.sidebar:
        st.markdown(
            '<div class="brand-lockup"><div class="brand-kicker">QUANTONG LABOR · LOCAL AI</div><div class="brand-name">全通劳务</div><div class="brand-note">招工信息工作台</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("### 访问认证")
        password = st.text_input("请输入访问密码", type="password", key="auth_password")
        if st.button("登录", use_container_width=True):
            if hmac.compare_digest(password, configured_password):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("密码错误")
    st.markdown(
        '<section class="auth-shell"><div class="auth-kicker">LOCAL RECRUITMENT WORKBENCH</div><h1>进入全通劳务招工助手</h1><p>在本地岗位库中快速查找工资、地点、住宿和入职要求。</p></section>',
        unsafe_allow_html=True,
    )
    st.stop()

jobs = get_jobs()
store = get_store()
active_model = resolve_model_name()
safe_model_name = html_module.escape(active_model)
ollama_status = check_ollama(model=active_model)
index_ready = (Path(__file__).resolve().parent / "chroma_db" / ".data_signature").exists()

with st.sidebar:
    st.markdown(
        '<div class="brand-lockup"><div class="brand-kicker">QUANTONG LABOR · LOCAL AI</div><div class="brand-name">全通劳务</div><div class="brand-note">招工信息工作台</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("### 本地运行状态")
    if ollama_status["available"] and ollama_status["model_ready"]:
        st.markdown(f'<span class="status-ready">Ollama 和 {safe_model_name} 已就绪</span>', unsafe_allow_html=True)
    elif ollama_status["available"]:
        st.markdown('<span class="status-wait">Ollama 已启动，但模型未找到</span>', unsafe_allow_html=True)
        st.code(f"ollama pull {active_model}", language="powershell")
    else:
        st.markdown('<span class="status-wait">Ollama 服务未连接</span>', unsafe_allow_html=True)
        st.code("ollama serve", language="powershell")

    st.caption("索引状态：已就绪" if index_ready else "索引状态：首次问答时构建 BGE + Chroma 索引")
    st.caption(f"本地 SQLite 会话记录：{store.message_count()} 条")
    st.divider()
    st.markdown("### 快捷提问")
    examples = ["有什么普工岗位？", "石岩附近工资多少？", "女生适合做什么？", "入职需要什么证件？"]
    for index, example in enumerate(examples):
        if st.button(example, key=f"example_{index}", use_container_width=True):
            st.session_state.pending_question = example

    st.divider()
    if st.button("清空当前对话", use_container_width=True):
        st.session_state.messages = initial_messages()
        st.session_state.pending_question = ""
        st.session_state.question_timestamps = []
        st.rerun()

    st.divider()
    if st.button("退出登录", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.messages = initial_messages()
        st.session_state.question_timestamps = []
        st.rerun()

st.markdown(
    """<section class="hero"><div class="hero-copy"><div class="hero-eyebrow">LOCAL RECRUITMENT WORKBENCH</div><h1>全通劳务招工助手</h1><p>把岗位信息问清楚，再决定下一步。工资、地点、住宿、班次和入职要求，都可以直接问小通。</p></div><div class="hero-visual"><div class="signal-board" aria-label="岗位数据概览"><div class="signal-bars"><i></i><i></i><i></i><i></i><i></i></div></div></div></section>""",
    unsafe_allow_html=True,
)
metrics = st.columns(3)
for column, label, value in zip(metrics, ("可查询岗位", "常见问题", "本地模型"), (str(len(jobs)), "30+", safe_model_name)):
    with column:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-rule"></div></div>', unsafe_allow_html=True)

st.markdown(
    '<div class="welcome-strip"><span class="welcome-dot"></span><strong>从一个具体问题开始</strong><span>例如“石岩附近有没有包吃住的普工岗位？”</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="workflow-grid"><div class="workflow-item"><div class="workflow-index">01</div><div><strong>说清你的需求</strong><span>地点、岗位、班次或住宿条件</span></div></div><div class="workflow-item"><div class="workflow-index">02</div><div><strong>让小通帮你筛</strong><span>从本地岗位库快速找到匹配项</span></div></div><div class="workflow-item"><div class="workflow-index">03</div><div><strong>查看岗位详情</strong><span>工资、福利和入职要求一次看全</span></div></div></div>',
    unsafe_allow_html=True,
)

chat_tab, jobs_tab = st.tabs(["智能问答", "浏览岗位"])

with chat_tab:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if message.get("sources"):
                with st.expander("本次回答参考"):
                    for source in message["sources"]:
                        st.caption(source)

    typed_question = st.chat_input("例如：石岩附近有没有包吃住的普工岗位？")
    question = typed_question or st.session_state.pending_question
    if question:
        question = question.strip()
        if len(question) > _MAX_QUESTION_LENGTH:
            st.session_state.pending_question = ""
            st.warning(f"单次提问请控制在 {_MAX_QUESTION_LENGTH} 个字符以内。")
            st.stop()
        # 限流：每分钟最多 _MAX_QUESTIONS_PER_MINUTE 次
        now = time.perf_counter()
        st.session_state.question_timestamps = [
            t for t in st.session_state.question_timestamps if now - t < 60.0
        ]
        if len(st.session_state.question_timestamps) >= _MAX_QUESTIONS_PER_MINUTE:
            wait_seconds = 60.0 - (now - st.session_state.question_timestamps[0])
            message = f"提问过于频繁，请等待 {int(wait_seconds) + 1} 秒后再试。"
            st.session_state.messages.append({"role": "assistant", "content": message, "sources": []})
            with st.chat_message("assistant"):
                st.warning(message)
            st.session_state.pending_question = ""
            st.rerun()
        st.session_state.question_timestamps.append(now)

        st.session_state.pending_question = ""
        st.session_state.messages.append({"role": "user", "content": question, "sources": []})
        store.save_message(st.session_state.conversation_id, "user", question)
        with st.chat_message("user"):
            st.write(question)
        try:
            started_at = time.perf_counter()
            with st.spinner("正在检索本地知识库..."):
                token_stream, sources = get_service().chat_stream(question, history_text(st.session_state.messages[:-1]))

            with st.chat_message("assistant"):
                # The service validates the complete model response before it
                # reaches the UI, so this is intentionally a single safe chunk.
                answer = st.write_stream(token_stream)
                answer = (answer or "").strip() or "这个问题需要转接人工客服确认。"
                if sources:
                    with st.expander("本次回答参考"):
                        for source in sources:
                            st.caption(source)
            elapsed = time.perf_counter() - started_at
            st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources})
            store.save_message(st.session_state.conversation_id, "assistant", answer, sources)
            st.session_state.last_elapsed = elapsed
        except Exception as error:
            # 生产环境：只给用户通用提示，详细日志写文件
            logger.error("AI service error", exc_info=True)
            message = "服务暂时不可用，请稍后重试或联系管理员。"
            st.session_state.messages.append({"role": "assistant", "content": message, "sources": []})
            store.save_message(st.session_state.conversation_id, "assistant", message)
            with st.chat_message("assistant"):
                st.error(message)

    if "last_elapsed" in st.session_state:
        st.caption(f"最近一次回答耗时：{st.session_state.last_elapsed:.2f} 秒")

with jobs_tab:
    location_options = ["全部地区"] + sorted({str(job["location"]).split("区")[0] + "区" for job in jobs})
    position_options = ["全部岗位"] + sorted({str(job["position"]) for job in jobs})
    filter_left, filter_right = st.columns(2)
    selected_location = filter_left.selectbox("工作地区", location_options)
    selected_position = filter_right.selectbox("岗位类型", position_options)
    visible_jobs = [
        job for job in jobs
        if (selected_location == "全部地区" or selected_location in str(job["location"]))
        and (selected_position == "全部岗位" or selected_position == job["position"])
    ]
    st.caption(f"找到 {len(visible_jobs)} 个符合条件的岗位")
    for job in visible_jobs:
        render_job(job)
