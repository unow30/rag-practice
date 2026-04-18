import os
from abc import ABC, abstractmethod
from typing import List

from langchain.schema import Document


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

            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": file_path,
                        "page": page_num + 1,
                        "doc_id": doc_id,
                        "section": None,
                        "version": None,
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

        pages = pymupdf4llm.to_markdown(file_path, page_chunks=True)

        if not pages:
            raise ValueError("이미지 기반 PDF는 현재 지원되지 않습니다.")

        docs: List[Document] = []
        for page_data in pages:
            text = page_data.get("text", "").strip()
            if not text:
                continue

            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": file_path,
                        "page": page_data.get("metadata", {}).get("page", 0) + 1,
                        "doc_id": doc_id,
                        "section": None,
                        "version": None,
                    },
                )
            )

        if not docs:
            raise ValueError("이미지 기반 PDF는 현재 지원되지 않습니다.")

        return docs


def get_extractor() -> BaseExtractor:
    extractor_type = os.getenv("EXTRACTOR", "pymupdf4llm").lower()
    if extractor_type == "pymupdf":
        return PyMuPDFExtractor()
    return PyMuPDF4LLMExtractor()
