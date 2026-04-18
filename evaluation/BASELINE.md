# v0 기준선 측정 가이드

## 측정 전 준비

1. 백엔드 서버 실행
   ```bash
   uvicorn backend.main:app --reload
   ```

2. 테스트 PDF 업로드 (Streamlit UI 또는 curl)
   ```bash
   curl -X POST http://localhost:8000/api/documents \
     -F "files=@your_test.pdf"
   ```

3. 문서 ID 확인
   ```bash
   curl http://localhost:8000/api/documents | python -m json.tool
   ```

4. 문서 상태가 READY가 될 때까지 대기 (최대 5분)
   ```bash
   watch -n 5 'curl -s http://localhost:8000/api/documents | python -m json.tool'
   ```

## 평가 실행

```bash
# 특정 문서 ID로 실행
python -m evaluation.run_eval --doc-ids <문서_ID> --output-name v0_baseline

# 전체 READY 문서 대상
python -m evaluation.run_eval --output-name v0_baseline
```

## 결과 확인

```bash
cat evaluation/results/v0_baseline.json | python -m json.tool
```

## 판단 기준

| 지표 | 목표 | 달성 시 | 미달 시 |
|------|------|---------|---------|
| Recall@5 | ≥ 80% | v3(Reranker)로 이동 | v1(BM25+RRF) 진행 |
| Answerable@5 | ≥ 80% | — | 청킹 전략 재검토 |
| Exact Match | ≥ 60% | — | 프롬프트 튜닝 |
| Latency (첫 토큰) | ≤ 3,000ms | — | 임베딩/검색 최적화 |

## v0 기준선 측정 결과

> 실제 측정 후 아래 표를 업데이트하세요.

| 지표 | v0 측정값 | 목표 | 달성 여부 |
|------|-----------|------|-----------|
| Recall@5 | — | ≥ 80% | — |
| Answerable@5 | — | ≥ 80% | — |
| Exact Match | — | ≥ 60% | — |
| Partial Match | — | ≥ 85% | — |
| Latency (첫 토큰) | — | ≤ 3,000ms | — |

## 다음 단계 결정

- Recall@5 ≥ 80% → **T-22 (Reranker)** 바로 진행
- Recall@5 < 80% → **T-17 (BM25 인덱싱)** 진행
