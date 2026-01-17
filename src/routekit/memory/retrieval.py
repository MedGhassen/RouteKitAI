"""Retrieval memory with TF-IDF/substring fallback."""

import re
from collections import Counter
from typing import Any

from pydantic import BaseModel

from routekit.core.memory import Memory


class RetrievalMemory(Memory):
    """Retrieval memory with TF-IDF or substring search fallback.

    For MVP, provides simple text-based retrieval without vector embeddings.
    """

    def __init__(self, use_tfidf: bool = True) -> None:
        """Initialize retrieval memory.

        Args:
            use_tfidf: Whether to use TF-IDF (True) or simple substring search (False)
        """
        self.use_tfidf = use_tfidf
        self._documents: list[dict[str, Any]] = []
        self._idf: dict[str, float] = {}

    async def get(self, key: str) -> Any:
        """Get document by ID.

        Args:
            key: Document ID

        Returns:
            Document data or None if not found
        """
        for doc in self._documents:
            if doc.get("id") == key:
                return doc
        return None

    async def set(self, key: str, value: Any) -> None:
        """Store document by ID.

        Args:
            key: Document ID
            value: Document data
        """
        if isinstance(value, dict):
            doc = value.copy()
            doc["id"] = key
        else:
            doc = {"id": key, "content": value}

        # Update or add document
        for i, existing_doc in enumerate(self._documents):
            if existing_doc.get("id") == key:
                self._documents[i] = doc
                self._update_idf()
                return

        self._documents.append(doc)
        self._update_idf()

    async def append(self, event: dict[str, Any]) -> None:
        """Append an event as a new document.

        Args:
            event: Event dictionary to append
        """
        import uuid

        doc_id = str(uuid.uuid4())
        doc = event.copy()
        doc["id"] = doc_id
        # Ensure content field exists for search (extract from event if needed)
        if "content" not in doc:
            # Try to extract content from event
            if isinstance(event, dict) and "content" in event:
                doc["content"] = event["content"]
            else:
                doc["content"] = str(event)
        self._documents.append(doc)
        self._update_idf()

    async def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Search documents using TF-IDF or substring matching.

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            List of matching documents with scores
        """
        if not self._documents:
            return []

        if self.use_tfidf:
            return await self._search_tfidf(query, k)
        else:
            return await self._search_substring(query, k)

    async def _search_tfidf(self, query: str, k: int) -> list[dict[str, Any]]:
        """Search using TF-IDF scoring.

        Args:
            query: Search query
            k: Number of results

        Returns:
            List of documents with TF-IDF scores
        """
        query_terms = self._tokenize(query)
        query_tf = Counter(query_terms)

        scores = []
        for doc in self._documents:
            content = str(doc.get("content", ""))
            doc_terms = self._tokenize(content)
            doc_tf = Counter(doc_terms)

            score = 0.0
            for term in query_terms:
                if term in doc_tf:
                    tf = doc_tf[term] / len(doc_terms) if doc_terms else 0
                    idf = self._idf.get(term, 0.0)
                    score += tf * idf

            if score > 0:
                result = doc.copy()
                result["score"] = score
                scores.append(result)

        # Sort by score descending
        scores.sort(key=lambda x: x.get("score", 0), reverse=True)
        return scores[:k]

    async def _search_substring(self, query: str, k: int) -> list[dict[str, Any]]:
        """Search using simple substring matching.

        Args:
            query: Search query
            k: Number of results

        Returns:
            List of matching documents
        """
        query_lower = query.lower()
        results = []

        for doc in self._documents:
            content = str(doc.get("content", "")).lower()
            if query_lower in content:
                result = doc.copy()
                result["score"] = 1.0  # Simple binary match
                results.append(result)
                if len(results) >= k:
                    break

        return results

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words.

        Args:
            text: Text to tokenize

        Returns:
            List of lowercase tokens
        """
        # Simple tokenization: lowercase, split on non-word chars
        tokens = re.findall(r"\b\w+\b", text.lower())
        return tokens

    def _update_idf(self) -> None:
        """Update inverse document frequency for all terms."""
        if not self._documents:
            self._idf = {}
            return

        doc_count = len(self._documents)
        term_doc_count: dict[str, int] = {}

        for doc in self._documents:
            content = str(doc.get("content", ""))
            terms = set(self._tokenize(content))
            for term in terms:
                term_doc_count[term] = term_doc_count.get(term, 0) + 1

        # Calculate IDF: log(total_docs / docs_with_term)
        self._idf = {
            term: __import__("math").log(doc_count / count) if count > 0 else 0.0
            for term, count in term_doc_count.items()
        }
