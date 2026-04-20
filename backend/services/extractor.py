import os
from abc import ABC, abstractmethod
from typing import List

from langchain.schema import Document


# PDF annot.type[0] 값 → 주석 유형 이름 매핑
_ANNOT_TYPE_MAP = {
    0: "memo",    # Text (팝업 메모)
    2: "memo",    # FreeText (인라인 메모)
    8: "highlight",
    9: "underline",
    11: "strikeout",
}


def _extract_annotations(page) -> dict:
    """fitz 페이지 객체에서 주석별 텍스트 스팬을 추출한다.

    Returns:
        {
            "annotations": {
                "highlight": ["텍스트1", "텍스트2"],
                "underline": ["텍스트3"],
                "strikeout": ["텍스트4"],
                "memo": [{"anchor": "주변 본문", "content": "메모 내용"}]
            },
            "memo_content": "메모1\n메모2"  # 전문 검색용
        }
        주석이 없으면 {"annotations": {}, "memo_content": None}
    """
    from collections import defaultdict

    buckets: dict = defaultdict(list)
    memo_parts: list[str] = []

    for annot in page.annots():
        type_id = annot.type[0]
        if type_id not in _ANNOT_TYPE_MAP:
            continue
        label = _ANNOT_TYPE_MAP[type_id]

        if type_id in (0, 2):  # Text / FreeText 메모
            content = annot.info.get("content", "").strip()
            if not content:
                continue
            anchor = page.get_text("text", clip=annot.rect).strip()
            buckets["memo"].append({"anchor": anchor, "content": content})
            memo_parts.append(content)
        else:  # highlight / underline / strikeout
            span = page.get_text("text", clip=annot.rect).strip()
            if span:
                buckets[label].append(span)

    return {
        "annotations": dict(buckets),
        "memo_content": "\n".join(memo_parts) if memo_parts else None,
    }


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, file_path: str, doc_id: str) -> List[Document]:
        """PDF에서 LangChain Document 목록을 반환한다."""


class PyMuPDFExtractor(BaseExtractor):
    """v0 베이스라인: fitz(PyMuPDF) 기반 페이지별 텍스트 추출"""

    def extract(self, file_path: str, doc_id: str) -> List[Document]:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError("PyMuPDF가 설치되지 않았습니다: pip install pymupdf")

        docs: List[Document] = []
        pdf = fitz.open(file_path)

        if len(pdf) == 0:
            raise ValueError("이미지 기반 PDF는 현재 지원되지 않습니다.")

        for page_num in range(len(pdf)):
            page = pdf[page_num]
            text = page.get_text("text").strip()

            if not text:
                continue

            annot_info = _extract_annotations(page)
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": file_path,
                        "page": page_num + 1,
                        "doc_id": doc_id,
                        "section": None,
                        "version": None,
                        **annot_info,
                    },
                )
            )

        pdf.close()

        if not docs:
            raise ValueError("이미지 기반 PDF는 현재 지원되지 않습니다.")

        return docs


class PyMuPDF4LLMExtractor(BaseExtractor):
    """v1 기본: pymupdf4llm 기반 Markdown 출력 (표 구조 보존)"""

    def extract(self, file_path: str, doc_id: str) -> List[Document]:
        try:
            import pymupdf4llm
        except ImportError:
            raise RuntimeError("pymupdf4llm이 설치되지 않았습니다: pip install pymupdf4llm")

        import fitz as _fitz

        pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)

        if not pages:
            raise ValueError("이미지 기반 PDF는 현재 지원되지 않습니다.")

        pdf = _fitz.open(file_path)
        docs: List[Document] = []
        for page_data in pages:
            text = page_data.get("text", "").strip()
            if not text:
                continue

            page_num = page_data.get("metadata", {}).get("page", 0)
            annot_info = _extract_annotations(pdf[page_num]) if page_num < len(pdf) else {"annotations": {}, "memo_content": None}
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": file_path,
                        "page": page_num + 1,
                        "doc_id": doc_id,
                        "section": None,
                        "version": None,
                        **annot_info,
                    },
                )
            )
        pdf.close()

        if not docs:
            raise ValueError("이미지 기반 PDF는 현재 지원되지 않습니다.")

        return docs


def get_extractor() -> BaseExtractor:
    extractor_type = os.getenv("EXTRACTOR", "pymupdf4llm").lower()
    if extractor_type == "pymupdf":
        return PyMuPDFExtractor()
    return PyMuPDF4LLMExtractor()
