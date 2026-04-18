import os
import re
from typing import List

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))

_TABLE_PATTERN = re.compile(r"\|[-:]+\|")


def _detect_content_type(text: str) -> str:
    if _TABLE_PATTERN.search(text):
        return "TABLE"
    return "TEXT"


def split_documents(docs: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    chunks: List[Document] = []
    for doc in docs:
        split = splitter.split_documents([doc])
        for chunk in split:
            chunk.metadata["content_type"] = _detect_content_type(chunk.page_content)
            chunks.append(chunk)

    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i

    return chunks
