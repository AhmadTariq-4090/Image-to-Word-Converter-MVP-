import os

import streamlit as st
from PIL import Image

from agents import ActionAgent, DecisionAgent, FeedbackAgent, PerceptionAgent
from memory import MemoryStore

st.set_page_config(
    page_title="🤖 Agentic Image-to-Word",
    layout="wide",
    page_icon="🤖",
)

# ── Agent initialization (cached for lifetime of server process) ──────────────
@st.cache_resource
def init_agents():
    mem = MemoryStore()
    return mem, PerceptionAgent(), DecisionAgent(), ActionAgent(), FeedbackAgent(mem)

memory, perception_agent, decision_agent, action_agent, feedback_agent = init_agents()

# ── Session state bootstrap ───────────────────────────────────────────────────
_DEFAULTS = {
    "session_id":      memory.new_session_id(),
    "image_analyses":  [],   # [{name, image, file_bytes, perception, decision}]
    "results":         [],   # [{text, confidence, engine, ...}]
    "converted":       False,
    "last_file_names": [],
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🤖 Agent Control Panel")
    st.caption(f"Session `{st.session_state.session_id}`")
    st.divider()

    st.subheader("⚙️ Configuration")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="Required only when the agent selects the Gemini engine.",
    )
    auto_convert = st.toggle("⚡ Auto-convert on upload", value=False)

    st.divider()
    st.subheader("🧠 Agent Memory")
    stats = memory.get_stats()
    c1, c2 = st.columns(2)
    c1.metric("Sessions", stats["total_sessions"])
    c2.metric("Corrections", stats["total_corrections"])
    st.metric("Avg Confidence", f"{stats['avg_confidence'] * 100:.0f}%")

    prefs = memory.get_engine_preferences()
    if prefs:
        st.caption("📊 Learned Preferences")
        for ct, p in prefs.items():
            st.caption(
                f"• **{ct}** → {p['preferred_engine']} "
                f"({p['usage_count']} samples, "
                f"{p['confidence'] * 100:.0f}% satisfaction)"
            )

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🤖 Agentic Image-to-Word Converter")
st.markdown(
    "An intelligent pipeline that **perceives** image quality, "
    "**decides** the best OCR engine, **acts** to convert, and "
    "**learns** from your feedback — fully agentic."
)

tab_convert, tab_memory, tab_logs = st.tabs(
    ["📤 Convert", "🧠 Memory & Learning", "📋 Logs"]
)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — CONVERT
# ═════════════════════════════════════════════════════════════════════════════
with tab_convert:

    # ── STEP 1: Input ─────────────────────────────────────────────────────────
    st.subheader("Step 1 › Input")
    in_tab_upload, in_tab_camera = st.tabs(["📤 Upload", "📸 Camera"])
    image_files = []

    with in_tab_upload:
        uploaded = st.file_uploader(
            "Upload Images (JPG/PNG)",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
        )
        if uploaded:
            image_files.extend(uploaded)

    with in_tab_camera:
        cam = st.camera_input("Take a photo")
        if cam:
            image_files.append(cam)

    # ── STEP 2: Perception Agent (auto-runs on new uploads) ───────────────────
    if image_files:
        st.divider()
        st.subheader("Step 2 › 🔍 Perception Agent")

        current_names = [f.name for f in image_files]
        if current_names != st.session_state.last_file_names:
            # New files — reset state and re-analyse
            st.session_state.image_analyses = []
            st.session_state.results        = []
            st.session_state.converted      = False
            st.session_state.last_file_names = current_names

            for f in image_files:
                img        = Image.open(f)
                perception = perception_agent.analyze(img)
                prefs      = memory.get_engine_preferences()
                decision   = decision_agent.decide(
                    perception, prefs, api_key_available=bool(api_key)
                )
                st.session_state.image_analyses.append({
                    "name":       f.name,
                    "image":      img,
                    "file_bytes": f.getvalue(),
                    "perception": perception,
                    "decision":   decision,
                })
                memory.log(
                    st.session_state.session_id, "INFO",
                    f"Perceived {f.name}: quality={perception['quality_score']}, "
                    f"type={perception['content_type']}, "
                    f"engine→{decision['engine']}",
                )

        # Display perception cards
        for analysis in st.session_state.image_analyses:
            p = analysis["perception"]
            with st.expander(
                f"📷 {analysis['name']}  —  Quality: {p['quality_score']}/100",
                expanded=True,
            ):
                col_img, col_info = st.columns([1, 2])
                with col_img:
                    st.image(analysis["image"], use_container_width=True)
                with col_info:
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Quality",      f"{p['quality_score']}/100")
                    m2.metric("Content Type", p["content_type"].replace("_", " ").title())
                    m3.metric("Sharpness",    f"{min(p['blur_score'], 999):.0f}")
                    if p["issues"]:
                        st.warning(f"⚠️ Issues: {', '.join(p['issues'])}")
                        if p["suggested_preprocessing"]:
                            st.info(f"🔧 Auto-preprocessing: {', '.join(p['suggested_preprocessing'])}")
                    else:
                        st.success("✅ Image quality is good")

        # ── STEP 3: Decision Agent ─────────────────────────────────────────────
        st.divider()
        st.subheader("Step 3 › 🧠 Decision Agent")

        for i, analysis in enumerate(st.session_state.image_analyses):
            d = analysis["decision"]
            col_info, col_override = st.columns([3, 1])
            icon = "⚡" if d["engine"] == "tesseract" else "🤖"
            with col_info:
                st.info(
                    f"{icon} **{analysis['name']}** → **{d['engine'].title()}**  \n"
                    f"Rationale: *{d['rationale']}*  \n"
                    f"Expected confidence: **{d['confidence_expected'] * 100:.0f}%**"
                )
            with col_override:
                override = st.selectbox(
                    "Override (Human-in-the-Loop)",
                    ["(Agent choice)", "tesseract", "gemini"],
                    key=f"override_{i}",
                )
                if override != "(Agent choice)":
                    st.session_state.image_analyses[i]["decision"]["engine"] = override
                    memory.log(
                        st.session_state.session_id, "INFO",
                        f"Human override: {analysis['name']} → {override}",
                    )

        # ── STEP 4: Action Agent ───────────────────────────────────────────────
        st.divider()
        st.subheader("Step 4 › ⚙️ Action Agent")

        convert_clicked = st.button(
            "🚀 Convert to Word Document",
            type="primary",
            use_container_width=True,
        )
        needs_gemini = any(
            a["decision"]["engine"] == "gemini"
            for a in st.session_state.image_analyses
        )

        if convert_clicked or (auto_convert and not st.session_state.converted):
            if needs_gemini and not api_key:
                st.error("❌ A Gemini API key is required. Add it in the sidebar or override the engine to Tesseract.")
            else:
                st.session_state.results  = []
                total_time = 0.0

                with st.spinner("Agent is processing…"):
                    progress = st.progress(0)
                    for idx, analysis in enumerate(st.session_state.image_analyses):
                        engine = analysis["decision"]["engine"]
                        img    = analysis["image"]

                        # Apply preprocessing if suggested
                        steps = analysis["decision"]["preprocessing"]
                        if steps:
                            img = perception_agent.preprocess(img, steps)

                        result          = action_agent.process(img, engine, api_key)
                        result["name"]  = analysis["name"]
                        result["image_hash"] = memory.hash_image(analysis["file_bytes"])
                        st.session_state.results.append(result)
                        total_time += result["processing_time"]

                        memory.log(
                            st.session_state.session_id,
                            "INFO" if result["success"] else "ERROR",
                            f"Processed {analysis['name']}: engine={engine}, "
                            f"confidence={result['confidence']}, "
                            f"time={result['processing_time']}s",
                        )
                        progress.progress((idx + 1) / len(st.session_state.image_analyses))

                if st.session_state.results:
                    avg_conf = sum(r["confidence"] for r in st.session_state.results) / len(st.session_state.results)
                    first    = st.session_state.image_analyses[0]
                    memory.save_session(
                        session_id      = st.session_state.session_id,
                        image_count     = len(st.session_state.results),
                        engine_used     = first["decision"]["engine"],
                        quality_score   = first["perception"]["quality_score"],
                        content_type    = first["perception"]["content_type"],
                        processing_time = total_time,
                        confidence      = avg_conf,
                    )
                    st.session_state.converted = True

        # ── STEP 5: Results + Download ─────────────────────────────────────────
        if st.session_state.results:
            st.divider()
            st.subheader("Step 5 › 📄 Results")

            avg_conf    = sum(r["confidence"] for r in st.session_state.results) / len(st.session_state.results)
            all_success = all(r["success"] for r in st.session_state.results)

            m1, m2, m3 = st.columns(3)
            m1.metric("Images Processed", len(st.session_state.results))
            m2.metric(
                "Avg Confidence", f"{avg_conf * 100:.0f}%",
                delta="Good" if avg_conf > 0.75 else "Low — Gemini may help",
            )
            m3.metric("Status", "✅ Success" if all_success else "⚠️ Partial")

            for result in st.session_state.results:
                dot = "🟢" if result["confidence"] > 0.75 else ("🟡" if result["confidence"] > 0.5 else "🔴")
                with st.expander(
                    f"{dot} {result['name']}  —  {result['engine'].title()}  |  "
                    f"Confidence: {result['confidence'] * 100:.0f}%  |  "
                    f"{result['word_count']} words  |  {result['processing_time']}s"
                ):
                    if result["success"]:
                        st.text_area(
                            "Extracted Text (editable preview)",
                            result["text"], height=200,
                            key=f"text_{result['name']}",
                        )
                    else:
                        st.error(result["text"])

            if all_success:
                docx_bytes = action_agent.generate_docx(st.session_state.results)
                st.download_button(
                    "⬇️ Download Word Document",
                    data=docx_bytes,
                    file_name="converted_document.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    type="primary",
                )

            # ── STEP 6: Feedback Agent ─────────────────────────────────────────
            st.divider()
            st.subheader("Step 6 › 💬 Feedback Agent — Teach the System")
            st.caption("Your feedback is stored in long-term memory and shapes future engine decisions.")

            fb_col1, fb_col2 = st.columns(2)
            with fb_col1:
                satisfied = st.radio("Was the output accurate?", ["👍 Yes", "👎 No"], horizontal=True)
                if st.button("Submit Feedback", key="btn_satisfaction"):
                    is_sat = satisfied == "👍 Yes"
                    for idx, result in enumerate(st.session_state.results):
                        analysis = st.session_state.image_analyses[idx]
                        feedback_agent.record_satisfaction(
                            session_id   = st.session_state.session_id,
                            engine_used  = result["engine"],
                            content_type = analysis["perception"]["content_type"],
                            satisfied    = is_sat,
                        )
                    st.success("✅ Feedback saved — agent will learn from this.")

            with fb_col2:
                names   = [r["name"] for r in st.session_state.results]
                target  = st.selectbox("Submit a text correction for:", names)
                corrected = st.text_area("Paste corrected text:", height=100)
                if st.button("Submit Correction", key="btn_correction") and corrected:
                    idx      = names.index(target)
                    result   = st.session_state.results[idx]
                    analysis = st.session_state.image_analyses[idx]
                    feedback_agent.record_correction(
                        session_id    = st.session_state.session_id,
                        image_hash    = result["image_hash"],
                        original_text = result["text"],
                        corrected_text = corrected,
                        engine_used   = result["engine"],
                        content_type  = analysis["perception"]["content_type"],
                    )
                    st.success("✅ Correction saved — agent will prefer a better engine next time.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — MEMORY & LEARNING
# ═════════════════════════════════════════════════════════════════════════════
with tab_memory:
    st.subheader("🧠 Long-Term Memory (SQLite)")

    prefs = memory.get_engine_preferences()
    if prefs:
        st.markdown("**Learned Engine Preferences**")
        st.table([
            {
                "Content Type":    ct,
                "Preferred Engine": p["preferred_engine"],
                "Satisfaction":    f"{p['confidence'] * 100:.0f}%",
                "Samples":         p["usage_count"],
            }
            for ct, p in prefs.items()
        ])
    else:
        st.info("No preferences learned yet. Convert images and submit feedback to teach the agent.")

    st.divider()
    st.markdown("**Recent Sessions**")
    sessions = memory.get_recent_sessions(10)
    if sessions:
        st.table(sessions)
    else:
        st.info("No sessions recorded yet.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — LOGS
# ═════════════════════════════════════════════════════════════════════════════
with tab_logs:
    st.subheader("📋 Processing Logs")
    col_filter, col_clear = st.columns([3, 1])
    show_session_only = col_filter.checkbox("Current session only", value=False)
    logs = memory.get_logs(
        session_id=st.session_state.session_id if show_session_only else None,
        limit=200,
    )
    if logs:
        for entry in logs:
            icon = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "🔴"}.get(entry["level"], "•")
            st.caption(f"{icon} `{entry['timestamp'][:19]}` — {entry['message']}")
    else:
        st.info("No logs yet.")
