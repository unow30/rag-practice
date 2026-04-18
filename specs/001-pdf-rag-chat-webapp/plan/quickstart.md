# Quickstart: PDF RAG 대화형 웹 앱

**Created**: 2026-04-18

---

## 사전 요구사항

- Python 3.11+
- 8GB+ RAM (BGE-M3 모델 로딩)
- Claude API 키 또는 OpenAI API 키

---

## 1. 환경 설정

```bash
# 저장소 클론
cd rag-practice

# Python 가상 환경 생성
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
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
# PDF 업로드
curl -X POST http://localhost:8000/api/documents \
  -F "files=@sample.pdf"

# 처리 상태 확인
curl http://localhost:8000/api/documents/{id}/status

# 질문 (스트리밍)
curl -N -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "문서의 주요 내용을 요약해 주세요.", "document_ids": []}'
```

---

## 7. 평가 실행

```bash
# 평가 셋 기반 성능 측정
python evaluation/run_eval.py --eval-set evaluation/eval_set.json --top-k 5
```

출력 예시:
```
Recall@5:       82.5%
Answerable@5:   77.5%
Exact Match:    63.0%
Partial Match:  87.0%
Avg Latency:    1,840ms
```
