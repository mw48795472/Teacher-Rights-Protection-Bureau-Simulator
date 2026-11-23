"""경량 하이브리드 검색: 문자 n-gram TF-IDF + BM25.

한국어 형태소 분석기 없이도 조사·어미 변화에 강하도록 문자 2~4-gram을 쓰고,
'제15조' 같은 정확한 키워드 매칭은 BM25가 받쳐준다. 임베딩 모델 다운로드가 필요 없다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

from collector.schema import Document


def _tokens(s: str) -> list[str]:
    words = re.findall(r"[0-9A-Za-z가-힣]+", s.lower())
    bigrams = [w[i:i + 2] for w in words for i in range(len(w) - 1)]
    return words + bigrams


@dataclass
class Hit:
    doc: Document
    score: float

    @property
    def citation(self) -> str:
        from .labels import tag_suffix
        tag = tag_suffix(self.doc, " · ")
        return f"[{self.doc.title}] 신뢰도 {self.doc.reliability}{tag}"


class Retriever:
    def __init__(self, docs: list[Document], alpha: float = 0.5):
        self.docs = docs
        self.alpha = alpha
        corpus = [f"{d.title} {d.article_no} {d.text}" for d in docs]
        self.tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
        self.mat = self.tfidf.fit_transform(corpus)
        self.bm25 = BM25Okapi([_tokens(c) for c in corpus])

    @staticmethod
    def _norm(x: np.ndarray) -> np.ndarray:
        rng = x.max() - x.min()
        return (x - x.min()) / rng if rng > 0 else np.zeros_like(x)

    def search(self, query: str, k: int = 5, source_types: set[str] | None = None) -> list[Hit]:
        dense = (self.mat @ self.tfidf.transform([query]).T).toarray().ravel()
        sparse = np.asarray(self.bm25.get_scores(_tokens(query)))
        score = self.alpha * self._norm(dense) + (1 - self.alpha) * self._norm(sparse)
        order = np.argsort(-score)
        hits = []
        for i in order:
            d = self.docs[i]
            if source_types and d.source_type not in source_types:
                continue
            if score[i] <= 0:
                break
            hits.append(Hit(d, float(score[i])))
            if len(hits) >= k:
                break
        return hits

    def by_article(self, article_no: str) -> Document | None:
        for d in self.docs:
            if d.source_type == "ordinance" and d.article_no == article_no:
                return d
        return None
