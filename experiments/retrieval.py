"""Deterministic local retrieval for controlled RAG experiments."""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str

    def render(self) -> str:
        return f"[{self.doc_id}] {self.title}: {self.text}"


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def retrieve_documents(
    query: str,
    top_k: int,
    corpus: list[Document],
    include_irrelevant: bool = False,
) -> list[Document]:
    if top_k <= 0:
        return []
    query_tokens = tokenize(query)
    scored = [
        (len(query_tokens & tokenize(document.text + " " + document.title)), document)
        for document in corpus
    ]
    ranked = [document for _, document in sorted(scored, key=lambda item: (-item[0], item[1].doc_id))]
    selected = ranked[:top_k]
    if include_irrelevant:
        irrelevant = [document for document in corpus if document not in selected][-1:]
        selected.extend(irrelevant)
    return selected


def render_retrieved_context(documents: list[Document]) -> str:
    return "\n".join(document.render() for document in documents)
