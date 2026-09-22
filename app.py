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
from knowledge_base import KnowledgeBase
from matching import match_candidate_to_jobs
from risk_engine import assess_project_risks


logger = logging.getLogger(__name__)

# 每会话每分钟最多提问次数（防止 CPU 推理被滥用）
_MAX_QUESTIONS_PER_MINUTE = 10
# 限制写入 SQLite 和发送给模型的单次输入大小，避免滥用本地推理资源。
_MAX_QUESTION_LENGTH = 500


st.set_page_config(page_title="全通劳务项目交付工作台", page_icon="AI", layout="wide", initial_sidebar_state="expanded")

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
    store = get_store()
    jobs_path = Path(__file__).resolve().parent / "data" / "jobs.json"
    store.sync_jobs_from_file(jobs_path, project_id=store.DEFAULT_PROJECT_ID)
    return store.list_jobs(project_id=store.DEFAULT_PROJECT_ID)


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
active_project = store.ensure_default_project()
project_id = str(active_project["id"])
active_model = resolve_model_name()
safe_model_name = html_module.escape(active_model)
ollama_status = check_ollama(model=active_model)
index_ready = (Path(__file__).resolve().parent / "chroma_db" / ".data_signature").exists()

with st.sidebar:
    st.markdown(
        '<div class="brand-lockup"><div class="brand-kicker">QUANTONG LABOR · PROJECT DELIVERY</div><div class="brand-name">全通劳务</div><div class="brand-note">项目交付与数据工作台</div></div>',
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
    st.caption(f"当前项目：{active_project['name']} · {active_project['client_name']}")
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
    """<section class="hero"><div class="hero-copy"><div class="hero-eyebrow">PROJECT DELIVERY WORKBENCH</div><h1>甲方外包用工交付工作台</h1><p>让岗位、候选人、派工与服务过程沉淀为自己的项目数据。RAG 用于查清业务依据，数据看板用于看清交付风险。</p></div><div class="hero-visual"><div class="signal-board" aria-label="项目交付数据概览"><div class="signal-bars"><i></i><i></i><i></i><i></i><i></i></div></div></div></section>""",
    unsafe_allow_html=True,
)
dashboard = store.dashboard_metrics(project_id)
metrics = st.columns(3)
for column, label, value in zip(metrics, ("项目岗位", "候选人报名", "已转为在岗工人"), (str(dashboard["jobs"]), str(dashboard["applications"]), str(dashboard["hired"]))):
    with column:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-rule"></div></div>', unsafe_allow_html=True)

st.markdown(
    '<div class="welcome-strip"><span class="welcome-dot"></span><strong>先看项目，再做交付</strong><span>岗位、候选人、派工、风险和操作证据均按项目沉淀。</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="workflow-grid"><div class="workflow-item"><div class="workflow-index">01</div><div><strong>沉淀业务数据</strong><span>候选人、报名与派工进入项目库</span></div></div><div class="workflow-item"><div class="workflow-index">02</div><div><strong>推进交付状态</strong><span>从推荐、面试到入场均可追溯</span></div></div><div class="workflow-item"><div class="workflow-index">03</div><div><strong>输出项目证据</strong><span>看板、风险和审计记录形成服务证明</span></div></div></div>',
    unsafe_allow_html=True,
)

dashboard_tab, chat_tab, jobs_tab, candidates_tab, delivery_tab, audit_tab = st.tabs(["项目驾驶舱", "项目问答", "岗位需求", "候选人与报名", "人员派工", "审计证据"])

with dashboard_tab:
    st.subheader(f"{active_project['name']} · 交付概览")
    st.caption("当前为本地演示项目。指标来自本项目 SQLite 业务记录，尚不包含薪酬、社保或瑞人云数据。")
    dashboard_columns = st.columns(5)
    dashboard_items = [
        ("岗位", dashboard["jobs"]),
        ("候选人", dashboard["candidates"]),
        ("推进中", dashboard["active_applications"]),
        ("已录用", dashboard["hired"]),
        ("报名转化", f"{dashboard['conversion_rate']}%"),
    ]
    for column, (label, value) in zip(dashboard_columns, dashboard_items):
        column.metric(label, value)

    applications_for_risk = store.list_applications(project_id)
    placements_for_risk = store.list_placements(project_id)
    risks = assess_project_risks(jobs, applications_for_risk, placements_for_risk)
    st.subheader("交付风险提醒")
    if not risks:
        st.success("当前规则未发现需要处理的交付风险。")
    else:
        for risk in risks:
            if risk["severity"] == "high":
                st.error(f"高风险 · {risk['title']}\n\n{risk['detail']}\n\n建议：{risk['action']}")
            else:
                st.warning(f"中风险 · {risk['title']}\n\n{risk['detail']}\n\n建议：{risk['action']}")

    st.subheader("在岗快照")
    snapshot_left, snapshot_right = st.columns(2)
    snapshot_date = snapshot_left.date_input("快照日期")
    on_duty_count = snapshot_right.number_input("当日在岗人数", min_value=0, step=1)
    if st.button("保存项目在岗快照", use_container_width=False):
        store.save_attendance_snapshot(snapshot_date.isoformat(), int(on_duty_count), project_id=project_id)
        st.success("在岗快照已保存，并已记入审计记录。")
        st.rerun()
    snapshots = store.list_attendance_snapshots(project_id, limit=7)
    if snapshots:
        st.dataframe(snapshots, use_container_width=True, hide_index=True)

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
        store.save_message(st.session_state.conversation_id, "user", question, project_id=project_id)
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
            store.save_message(st.session_state.conversation_id, "assistant", answer, sources, project_id=project_id)
            st.session_state.last_elapsed = elapsed
        except Exception as error:
            # 生产环境：只给用户通用提示，详细日志写文件
            logger.error("AI service error", exc_info=True)
            message = "服务暂时不可用，请稍后重试或联系管理员。"
            st.session_state.messages.append({"role": "assistant", "content": message, "sources": []})
            store.save_message(st.session_state.conversation_id, "assistant", message, project_id=project_id)
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

with candidates_tab:
    st.subheader("候选人登记")
    st.caption("手机号仅保存哈希和后四位，用于本地业务去重和人工联系提示。")
    with st.form("candidate_registration", clear_on_submit=True):
        first_row, second_row = st.columns(2)
        candidate_name = first_row.text_input("姓名", placeholder="例如：张三")
        candidate_phone = second_row.text_input("手机号", placeholder="仅用于联系，不会明文入库")
        third_row, fourth_row, fifth_row = st.columns(3)
        candidate_age = third_row.number_input("年龄", min_value=16, max_value=70, value=25, step=1)
        candidate_gender = fourth_row.selectbox("性别", ["未说明", "男", "女"])
        candidate_location = fifth_row.text_input("期望地区", placeholder="例如：石岩")
        candidate_position = st.text_input("期望岗位", placeholder="例如：普工")
        candidate_skills = st.text_input("技能或经历", placeholder="例如：电子厂经验、包装、叉车证")
        candidate_submitted = st.form_submit_button("登记候选人", use_container_width=True)
    if candidate_submitted:
        try:
            candidate_id = store.create_candidate(
                candidate_name,
                candidate_phone,
                int(candidate_age),
                candidate_gender,
                candidate_location,
                candidate_position,
                candidate_skills,
                project_id=project_id,
            )
            st.success(f"候选人已登记，编号 #{candidate_id}。")
            st.rerun()
        except ValueError as error:
            st.error(str(error))

    candidates = store.list_candidates(project_id)
    if not candidates:
        st.info("还没有候选人，请先完成登记。")
    else:
        st.divider()
        st.subheader("候选人匹配推荐")
        candidate_options = {f"#{item['id']} {item['name']} · {item['preferred_position'] or '未填写'}": item for item in candidates}
        selected_label = st.selectbox("选择候选人", list(candidate_options))
        selected_candidate = candidate_options[selected_label]
        recommendations = match_candidate_to_jobs(selected_candidate, jobs, limit=5)
        if not recommendations:
            st.warning("当前岗位库没有满足地区、岗位或技能条件的推荐结果。")
        for recommendation in recommendations:
            job = recommendation["job"]
            reason = "、".join(recommendation["reasons"])
            match_left, match_right = st.columns([5, 1])
            with match_left:
                st.markdown(f"**{job['factory_name']} · {job['position']}**　匹配度 {recommendation['score']} / 100")
                st.caption(f"{job['location']} · {job['salary']} · {reason}")
            with match_right:
                if st.button("报名", key=f"apply_{selected_candidate['id']}_{job['id']}", use_container_width=True):
                    application_id = store.create_application(int(selected_candidate["id"]), int(job["id"]), project_id=project_id)
                    st.success(f"报名记录 #{application_id} 已保存")
                    st.rerun()

    applications = store.list_applications(project_id)
    if applications:
        st.divider()
        st.subheader("报名状态")
        statuses = {"applied": "已报名", "interview": "面试中", "hired": "已入职", "rejected": "未录用", "withdrawn": "已撤回"}
        for application in applications:
            status_values = list(statuses)
            current_index = status_values.index(application["status"])
            status_key = f"status_{application['id']}"
            selected_status = st.selectbox(
                f"#{application['id']} {application['name']} → {application['factory_name']} · {application['position']}",
                status_values,
                index=current_index,
                format_func=lambda value: statuses[value],
                key=status_key,
            )
            if selected_status != application["status"]:
                store.update_application_status(int(application["id"]), selected_status, project_id=project_id)
                st.rerun()

with delivery_tab:
    st.subheader("人员派工与生命周期")
    st.caption("借鉴成熟 HRMS 的生命周期思路；当前只保存最小业务字段，不接入身份证、薪资或社保明细。")
    candidates = store.list_candidates(project_id)
    workers = store.list_workers(project_id)
    if candidates:
        candidate_options = {f"#{item['id']} {item['name']} · {item['preferred_position'] or '未填写'}": item for item in candidates}
        selected_worker_label = st.selectbox("选择候选人转入工人主档", list(candidate_options), key="worker_candidate")
        if st.button("建立工人主档", key="promote_worker"):
            worker_id = store.promote_candidate_to_worker(int(candidate_options[selected_worker_label]["id"]), project_id=project_id)
            st.success(f"工人主档 #{worker_id} 已建立。")
            st.rerun()
    if workers:
        worker_options = {f"#{item['id']} {item['name']} · {item['lifecycle_status']}": item for item in workers}
        selected_worker = st.selectbox("选择工人", list(worker_options), key="placement_worker")
        selected_job = st.selectbox("选择派工岗位", jobs, format_func=lambda job: f"#{job['id']} {job['factory_name']} · {job['position']}", key="placement_job")
        if st.button("创建派工记录", key="create_placement"):
            placement_id = store.create_placement(int(worker_options[selected_worker]["id"]), int(selected_job["id"]), project_id=project_id)
            st.success(f"派工记录 #{placement_id} 已创建。")
            st.rerun()
    placements = store.list_placements(project_id)
    if placements:
        st.divider()
        st.subheader("派工状态时间线")
        placement_statuses = {"pending": "待入场", "onboarded": "已入场", "separated": "已离场", "cancelled": "已取消"}
        for placement in placements:
            status_values = list(placement_statuses)
            selected_status = st.selectbox(
                f"#{placement['id']} {placement['name']} → {placement['factory_name']} · {placement['position']}",
                status_values,
                index=status_values.index(placement["status"]),
                format_func=lambda value: placement_statuses[value],
                key=f"placement_status_{placement['id']}",
            )
            reason = st.text_input("离场原因（如适用）", value=placement.get("separation_reason", ""), key=f"placement_reason_{placement['id']}")
            if selected_status != placement["status"] or reason != placement.get("separation_reason", ""):
                if st.button("保存派工状态", key=f"save_placement_{placement['id']}"):
                    store.update_placement_status(int(placement["id"]), selected_status, reason, project_id=project_id)
                    st.rerun()
        st.dataframe(placements, use_container_width=True, hide_index=True)
    else:
        st.info("还没有派工记录。先在候选人与报名页登记候选人，再建立工人主档。")

with audit_tab:
    st.subheader("审计证据时间线")
    st.caption("当前实现是本地追加写入的哈希链演示；生产环境仍需独立审计存储、密钥托管和访问审批。")
    events = store.list_audit_events(project_id, limit=100)
    if events:
        st.dataframe(events, use_container_width=True, hide_index=True)
    else:
        st.info("项目还没有审计事件。")
