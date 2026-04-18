# Quickstart: PDF RAG 대화형 웹 앱

**Created**: 2026-04-18

---

## 사전 요구사항

- Python 3.11 ~ 3.13 권장 (3.14+는 ML 패키지 호환성 미보장)
- 8GB+ RAM (BGE-M3 모델 로딩)
- Claude API 키 또는 OpenAI API 키

> **macOS (Homebrew) 사용자**: `python`, `pip` 대신 `python3`, `pip3` 또는 명시적 버전 경로를 사용한다.
> Python 3.13 설치: `brew install python@3.13`

---

## 1. 환경 설정

```bash
# 저장소 루트로 이동
cd rag-practice

# Python 가상 환경 생성 (macOS Homebrew 기준)
/opt/homebrew/opt/python@3.13/bin/python3 -m venv .venv

# Linux / 일반 환경
# python3 -m venv .venv

# 가상환경 활성화
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# pip 업그레이드 후 의존성 설치
pip install --upgrade pip
pip install -r requirements.txt
```

**주요 의존성** (`requirements.txt`):
```
fastapi
uvicorn[standard]
pymupdf4llm
langchain
langchain-community
faiss-cpu
rank_bm25
sentence-transformers   # BGE-M3
FlagEmbedding           # BGE-M3 + reranker
sqlalchemy
python-multipart
anthropic               # Claude API (또는 openai)
streamlit               # 프론트엔드 (v0)
```

---

## 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일 편집:
```env
# LLM API (둘 중 하나)
ANTHROPIC_API_KEY=your-claude-api-key
# OPENAI_API_KEY=your-openai-api-key

# 모델 설정
LLM_MODEL=claude-sonnet-4-6          # 또는 gpt-4o
EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=BAAI/bge-reranker-v2-m3

# 저장 경로
DATA_DIR=./data
DB_PATH=./data/rag.db

# RAG 파라미터
CHUNK_SIZE=800
CHUNK_OVERLAP=120
RETRIEVAL_TOP_K=20
RERANK_TOP_N=5
```

---

## 3. 데이터 디렉터리 초기화

```bash
mkdir -p data/documents data/indexes
```

---

## 4. 서버 실행

```bash
# 백엔드 (FastAPI)
uvicorn backend.main:app --reload --port 8000

# 프론트엔드 (Streamlit, 별도 터미널)
streamlit run frontend/app.py --server.port 8501
```

---

## 5. 접속

- **앱**: http://localhost:8501
- **API 문서**: http://localhost:8000/docs

---

## 6. 빠른 동작 확인 (cURL)

```bash
# 헬스체크
curl http://localhost:8000/health
# → {"status": "ok"}

# PDF 업로드
curl -X POST http://localhost:8000/api/documents \
  -F "files=@sample.pdf"

# 문서 목록 조회 (doc_id 확인)
curl http://localhost:8000/api/documents

# 처리 상태 확인 (status: READY 가 될 때까지 반복)
curl http://localhost:8000/api/documents/<doc_id>/status

# 질문 (SSE 스트리밍)
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "문서의 주요 내용을 요약해 주세요.", "document_ids": ["<doc_id>"]}'
```

---

## 7. 자동화 테스트 (pytest)

```bash
# 업로드 API 통합 테스트 실행
pytest backend/tests/test_upload_api.py -v
```

예상 결과:
```
test_health                PASSED
test_upload_invalid_type   PASSED
test_upload_too_large      PASSED
test_list_documents_empty  PASSED
```

---

## 8. RAG 품질 평가

```bash
# 전체 READY 문서 대상 평가
python -m evaluation.run_eval --output-name v0_baseline

# 특정 문서만 평가
python -m evaluation.run_eval --doc-ids <doc_id> --output-name v0_baseline

# 결과 파일 확인
cat evaluation/results/v0_baseline.json
```

출력 예시:
```
📊 평가 결과 요약
  Recall@5     : 72.50%
  Answerable@5 : 68.00%
  Exact Match  : 45.00%
  Partial Match: 60.00%
  Latency (첫 토큰): 1,842ms

🎯 목표 달성 여부
  ✅ Latency ≤ 3000ms
  ❌ Recall@5 ≥ 80% → v1(BM25+RRF) 진행 필요
```

결과에 따른 다음 단계:
- **Recall@5 ≥ 80%** → v3 Reranker(T-22) 바로 진행
- **Recall@5 < 80%** → v1 BM25+RRF(T-17) 진행

> 측정 결과는 `evaluation/BASELINE.md` 에 기록하세요.
