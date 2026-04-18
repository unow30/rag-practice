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

**측정일**: 2026-04-18  
**문서**: 대신증권 FICC 투자 리포트 (`20260310_invest_161558000.pdf`, 3페이지)  
**결과 파일**: `evaluation/results/v0_baseline.json`

| 지표 | v0 측정값 | 목표 | 달성 여부 |
|------|-----------|------|-----------|
| Recall@5 | 0.00% | ≥ 80% | ❌ 미달 |
| Answerable@5 | 0.00% | ≥ 80% | ❌ 미달 |
| Exact Match | 0.00% | ≥ 60% | ❌ 미달 |
| Partial Match | 25.56% | ≥ 85% | ❌ 미달 |
| Latency (첫 토큰) | 3,031ms | ≤ 3,000ms | ❌ 미달 |

## 다음 단계 결정

- Recall@5 = 0.00% < 80% → **T-17 (BM25 인덱싱)** 진행 (완료)  
- ✅ T-17, T-18 완료 → v1 (앙상블 검색) 평가 진행

---

## v1 기준선 측정 결과 (RETRIEVER=ensemble)

**측정일**: 2026-04-18  
**결과 파일**: `evaluation/results/v1_ensemble.json`

| 지표 | v1 측정값 | v0 대비 | 목표 | 달성 여부 |
|------|-----------|---------|------|-----------|
| Recall@5 | 61.54% | +61.54%p | ≥ 80% | ❌ 미달 |
| Answerable@5 | 78.89% | +78.89%p | ≥ 80% | ❌ 미달 |
| Exact Match | 0.00% | 0%p | ≥ 60% | ❌ 미달 |
| Partial Match | 86.67% | +61.11%p | ≥ 85% | ✅ 달성 |
| Latency (첫 토큰) | 8,529ms | +5,498ms | ≤ 3,000ms | ❌ 미달 |

**판단**: Recall@5 = 61.54% < 80%, 표현 불일치 질문 Recall 개선 필요 → **v2 (Multi-query) 진행**

## v2 기준선 측정 결과 (MULTI_QUERY=true)

**측정일**: 2026-04-18  
**결과 파일**: `evaluation/results/v2_multiquery.json`

| 지표 | v2 측정값 | v1 대비 | 목표 | 달성 여부 |
|------|-----------|---------|------|-----------|
| Recall@5 | 61.54% | 0%p | ≥ 80% | ❌ 미달 |
| Partial Match | 86.67% | 0%p | ≥ 85% | ✅ 달성 |
| Latency (첫 토큰) | 9,247ms | +718ms | ≤ 3,000ms | ❌ 미달 |

**판단**: Multi-query 효과 없음 (Recall 동일, Latency 증가) → **v3 (Reranker) 진행**

---

## 최종 평가 결과 (전체 파이프라인: RETRIEVER=ensemble + Reranker)

**측정일**: 2026-04-18  
**결과 파일**: `evaluation/results/final.json`

| 지표 | 최종값 | 목표 | 달성 여부 |
|------|--------|------|-----------|
| Recall@5 | 61.54% | ≥ 80% | ❌ 미달 |
| Answerable@5 | 76.67% | ≥ 80% | ❌ 미달 |
| Exact Match | 0.00% | ≥ 60% | ❌ 미달 |
| Partial Match | 85.00% | ≥ 85% | ✅ 달성 |
| Latency (첫 토큰) | 22,294ms* | ≤ 3,000ms | ❌ 미달 |

> *Latency는 Reranker 모델 첫 로드(약 170s) 포함 값. 서버 운영 환경에서 모델 캐시 후 실 응답은 10~25s 수준.

### 분석 메모

- **Recall 61.54%**: TABLE 카테고리(Q6~Q9, Q12) 5문항 전부 Recall=0 — 업종별 수익률이 이미지/그래프로 삽입되어 텍스트 추출 안 됨. OCR 적용 필요.
- **Exact Match 0%**: `expected_answer`가 구체적 수치 포함 문장으로 LLM 답변 표현과 다름 — partial_match 방식으로만 유효.
- **Partial Match 85%**: 목표 달성.
- **다음 개선 방향**: OCR 파이프라인 추가 시 TABLE 카테고리 Recall 대폭 향상 예상.
