import json
import os
import time

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="PDF RAG 질의응답", page_icon="📄", layout="wide")

# ── 세션 상태 초기화 ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "selected_doc_ids" not in st.session_state:
    st.session_state.selected_doc_ids = []
if "reindexing_doc_ids" not in st.session_state:
    st.session_state.reindexing_doc_ids = set()


# ── 헬퍼 함수 ────────────────────────────────────────────────────
def fetch_documents():
    try:
        resp = requests.get(f"{API_BASE}/api/documents", timeout=5)
        return resp.json().get("documents", [])
    except Exception:
        return []


def upload_files(files):
    try:
        file_tuples = [("files", (f.name, f.getvalue(), "application/pdf")) for f in files]
        resp = requests.post(f"{API_BASE}/api/documents", files=file_tuples, timeout=30)
        return resp.status_code, resp.json()
    except Exception as e:
        return 500, {"error": str(e)}


def delete_document(doc_id: str):
    try:
        resp = requests.delete(f"{API_BASE}/api/documents/{doc_id}", timeout=5)
        return resp.status_code
    except Exception:
        return 500


def fetch_file_status(doc_id: str) -> bool:
    """파일이 마지막 처리 이후 변경되었으면 True를 반환한다."""
    try:
        resp = requests.get(f"{API_BASE}/api/documents/{doc_id}/file-status", timeout=5)
        return resp.json().get("changed", False)
    except Exception:
        return False


def reindex_document(doc_id: str) -> int:
    try:
        resp = requests.post(f"{API_BASE}/api/documents/{doc_id}/reindex", timeout=10)
        return resp.status_code
    except Exception:
        return 500


def poll_status(doc_id: str) -> dict:
    try:
        resp = requests.get(f"{API_BASE}/api/documents/{doc_id}/status", timeout=5)
        return resp.json()
    except Exception:
        return {"status": "UNKNOWN"}


def status_badge(status: str) -> str:
    badges = {
        "PENDING": "⏳ 대기",
        "EXTRACTING": "🔍 추출 중",
        "CHUNKING": "✂️ 분할 중",
        "EMBEDDING": "🧠 임베딩 중",
        "READY": "✅ 준비됨",
        "FAILED": "❌ 실패",
    }
    return badges.get(status, status)


def _doc_name_html(name: str, max_len: int = 25) -> str:
    """긴 문서명은 생략(…)하고, 마우스 호버 시 전체명을 tooltip으로 표시한다."""
    safe = name.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    if len(name) <= max_len:
        return f"<b>{safe}</b>"
    short = name[:max_len] + "…"
    short_safe = short.replace("&", "&amp;").replace("<", "&lt;")
    return f'<span title="{safe}" style="cursor:default"><b>{short_safe}</b></span>'


# ── 사이드바 ─────────────────────────────────────────────────────
with st.sidebar:
    st.title("📄 문서 관리")

    # 파일 업로드
    uploaded = st.file_uploader(
        "PDF 파일 업로드 (최대 5개, 50MB)",
        type=["pdf"],
        accept_multiple_files=True,
        key="uploader",
    )
    if st.button("업로드", disabled=not uploaded):
        with st.spinner("업로드 중..."):
            code, result = upload_files(uploaded)
        if code == 202:
            new_docs = result.get("documents", [])
            duplicates = result.get("duplicates", [])
            if new_docs:
                st.success(f"✓ {len(new_docs)}개 파일 업로드 완료. 처리 중입니다...")
            for dup in duplicates:
                st.warning(f"⚠ {dup['name']} — 이미 업로드된 문서입니다 (중복 제외)")
            if new_docs or duplicates:
                st.rerun()
        else:
            detail = result.get("detail", result)
            msg = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
            st.error(msg)

    st.divider()

    # 문서 목록
    docs = fetch_documents()
    docs_by_id = {d["id"]: d for d in docs}

    # 재처리 완료/실패 알림
    finished = set()
    for doc_id in st.session_state.reindexing_doc_ids:
        doc = docs_by_id.get(doc_id)
        if doc and doc["status"] == "READY":
            st.success(f"✓ '{doc['name']}' 재처리가 완료되었습니다.")
            finished.add(doc_id)
        elif doc and doc["status"] == "FAILED":
            st.error(f"✗ '{doc['name']}' 재처리에 실패했습니다.")
            finished.add(doc_id)
    st.session_state.reindexing_doc_ids -= finished

    processing = [d for d in docs if d["status"] not in ("READY", "FAILED")]
    if processing:
        st.info(f"{len(processing)}개 문서 처리 중... (자동 새로고침)")
        time.sleep(2)
        st.rerun()

    st.subheader("문서 목록")
    if not docs:
        st.caption("업로드된 문서가 없습니다.")
    else:
        ready_docs = [d for d in docs if d["status"] == "READY"]
        selected = st.multiselect(
            "질의 대상 문서 선택 (미선택 시 전체)",
            options=[d["id"] for d in ready_docs],
            format_func=lambda did: next((d["name"] for d in ready_docs if d["id"] == did), did),
            default=st.session_state.selected_doc_ids,
        )
        st.session_state.selected_doc_ids = selected

        # READY 문서만 변경 여부 확인 (처리 중인 문서는 제외)
        changed_ids = {
            doc["id"]
            for doc in docs
            if doc["status"] == "READY" and fetch_file_status(doc["id"])
        }

        for doc in docs:
            is_changed = doc["id"] in changed_ids
            is_processing = doc["status"] not in ("READY", "FAILED")
            show_reindex = doc["status"] == "FAILED" or (doc["status"] == "READY" and is_changed)
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            with col1:
                change_badge = " · 📝 변경됨" if is_changed else ""
                st.markdown(
                    f"{_doc_name_html(doc['name'])}  \n"
                    f"<small>{status_badge(doc['status'])}{change_badge} · "
                    f"{doc.get('page_count') or '?'} 페이지 · "
                    f"{round(doc['size_bytes'] / 1024 / 1024, 1)} MB</small>",
                    unsafe_allow_html=True,
                )
                if is_processing:
                    status_info = poll_status(doc["id"])
                    pct = status_info.get("progress", 0) / 100
                    msg = status_info.get("progress_message", "")
                    st.progress(pct, text=msg)
            with col2:
                if doc["status"] in ("READY", "FAILED"):
                    file_url = f"{API_BASE}/api/documents/{doc['id']}/file"
                    st.link_button("📄", file_url, help="PDF 열기")
            with col3:
                if show_reindex:
                    if st.button("🔄", key=f"reindex_{doc['id']}", help="재처리"):
                        code = reindex_document(doc["id"])
                        if code == 202:
                            st.session_state.reindexing_doc_ids.add(doc["id"])
                            st.rerun()
                        elif code == 409:
                            st.warning("이미 처리 중입니다.")
                        else:
                            st.error("재처리 요청에 실패했습니다.")
            with col4:
                if st.button("🗑", key=f"del_{doc['id']}"):
                    delete_document(doc["id"])
                    st.rerun()

    st.divider()

    if st.button("대화 초기화"):
        if st.session_state.conversation_id:
            try:
                requests.delete(f"{API_BASE}/api/chat/{st.session_state.conversation_id}", timeout=5)
            except Exception:
                pass
        st.session_state.messages = []
        st.session_state.conversation_id = None
        st.rerun()


# ── 메인 영역: 대화창 ─────────────────────────────────────────────
st.title("💬 PDF 문서 질의응답")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander("📎 출처 보기"):
                for src in msg["sources"]:
                    st.markdown(
                        f"- **{src['document_name']}** — {src['page_number']}페이지  \n"
                        f"  _{src['content_snippet'][:120]}..._"
                    )

question = st.chat_input("문서에 대해 질문하세요...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_answer = []
        sources = []
        error_msg = None

        try:
            payload = {
                "conversation_id": st.session_state.conversation_id,
                "question": question,
                "document_ids": st.session_state.selected_doc_ids or None,
            }
            with requests.post(
                f"{API_BASE}/api/chat",
                json=payload,
                stream=True,
                timeout=35,
            ) as resp:
                if resp.status_code != 200:
                    try:
                        detail = resp.json().get("detail", {})
                        error_msg = detail.get("message", "오류가 발생했습니다.") if isinstance(detail, dict) else str(detail)
                    except Exception:
                        error_msg = f"서버 오류 ({resp.status_code})"
                else:
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                        if line_str.startswith("data:"):
                            data_str = line_str[5:].strip()
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            if "token" in data:
                                full_answer.append(data["token"])
                                placeholder.markdown("".join(full_answer) + "▌")
                            elif "conversation_id" in data:
                                st.session_state.conversation_id = data["conversation_id"]
                                sources = data.get("sources", [])
                                placeholder.markdown("".join(full_answer))
                            elif "error" in data:
                                error_msg = data.get("message", "오류가 발생했습니다.")

        except requests.exceptions.Timeout:
            error_msg = "AI 서비스가 응답하지 않습니다. 재시도해 주세요."
        except Exception as e:
            error_msg = f"연결 오류: {e}"

        if error_msg:
            placeholder.error(error_msg)
            col1, col2 = st.columns([1, 5])
            with col1:
                if st.button("🔄 재시도"):
                    st.rerun()
        else:
            answer = "".join(full_answer)
            if sources:
                with st.expander("📎 출처 보기"):
                    for src in sources:
                        st.markdown(
                            f"- **{src['document_name']}** — {src['page_number']}페이지  \n"
                            f"  _{src['content_snippet'][:120]}..._"
                        )
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "sources": sources,
            })
