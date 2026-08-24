from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from workflow.graph import build_workflow  # noqa: E402


st.set_page_config(page_title="OrgMind Agentic RAG", page_icon="🧠", layout="wide")
st.title("OrgMind Agentic RAG")
st.caption("Agentic retrieval over Acme AI organizational knowledge")


@st.cache_resource
def get_agent():
    return build_workflow()


with st.form("question_form"):
    question = st.text_input(
        "Ask a question",
        placeholder=(
            "Who worked on Project Phoenix and also has Kubernetes experience?"
        ),
    )
    submitted = st.form_submit_button("Ask OrgMind", type="primary")

if submitted:
    clean_question = question.strip()
    if not clean_question:
        st.warning("Enter a question first.")
    else:
        try:
            with st.spinner("Planning, retrieving, and grounding the answer..."):
                st.session_state["last_result"] = get_agent().invoke(
                    {"question": clean_question}
                )
            st.session_state.pop("last_error", None)
        except Exception as exc:
            st.session_state["last_error"] = str(exc)
            st.session_state.pop("last_result", None)

if "last_error" in st.session_state:
    st.error("OrgMind could not complete the request.")
    with st.expander("Error details"):
        st.code(st.session_state["last_error"])

if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    route = str(result.get("route", "unknown")).title()
    replanned = bool(result.get("replanned", False))

    st.subheader("Your question")
    st.write(result["question"])

    route_col, replan_col, attempts_col = st.columns(3)
    route_col.metric("Route chosen", route)
    replan_col.metric("Agent replanned", "Yes" if replanned else "No")
    attempts_col.metric("Retrieval attempts", result.get("attempts", 1))

    st.subheader("Grounded answer")
    st.success(result.get("answer", "No answer was generated."))

    with st.expander("Evidence and debug details"):
        graph_results = result.get("graph_results", [])
        vector_results = result.get("vector_results", [])

        st.markdown("#### Route history")
        st.json(result.get("route_history", []), expanded=True)

        st.markdown("#### Evidence-grader history")
        st.json(result.get("grader_history", []), expanded=False)

        st.markdown(f"#### Graph evidence ({len(graph_results)} rows)")
        if graph_results:
            st.dataframe(graph_results, use_container_width=True, hide_index=True)
        else:
            st.caption("No graph evidence was used.")

        st.markdown(f"#### Vector evidence ({len(vector_results)} passages)")
        if not vector_results:
            st.caption("No vector evidence was used.")
        for item in vector_results:
            source = item.get("file_name") or "Unknown source"
            score = item.get("score")
            score_label = f" · score {score:.4f}" if score is not None else ""
            with st.expander(f"{source}{score_label}"):
                st.write(item.get("text", ""))
                st.json(
                    {
                        key: value
                        for key, value in item.items()
                        if key != "text"
                    },
                    expanded=False,
                )
