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


POLICY_CORPUS = [
    Document(
        "policy-remote",
        "Flexible Work Policy",
        "Remote work eligibility is covered by the Flexible Work Policy. Employees need manager approval.",
    ),
    Document(
        "policy-ai-tools",
        "External AI Tool Use",
        "External AI tools require project owner approval before confidential data may be entered.",
    ),
    Document(
        "policy-incidents",
        "Incident Retention",
        "Incident records are retained for two years after closure unless legal review requires longer retention.",
    ),
    Document(
        "policy-travel",
        "Travel Reimbursement",
        "Travel receipts must be submitted within thirty days and are unrelated to AI tool approval.",
    ),
    Document(
        "policy-hardware",
        "Hardware Support",
        "Hardware replacement requests are handled by the support desk and do not affect incident retention.",
    ),
]


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def retrieve_documents(query: str, top_k: int, include_irrelevant: bool = False) -> list[Document]:
    if top_k <= 0:
        return []
    query_tokens = tokenize(query)
    scored = [
        (len(query_tokens & tokenize(document.text + " " + document.title)), document)
        for document in POLICY_CORPUS
    ]
    ranked = [document for _, document in sorted(scored, key=lambda item: (-item[0], item[1].doc_id))]
    selected = ranked[:top_k]
    if include_irrelevant:
        irrelevant = [document for document in POLICY_CORPUS if document not in selected][-1:]
        selected.extend(irrelevant)
    return selected


def render_retrieved_context(documents: list[Document]) -> str:
    return "\n".join(document.render() for document in documents)
