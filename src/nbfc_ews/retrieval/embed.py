"""Turning text into vectors.

Two methods, never one. Some embedding models are trained asymmetrically- a 
question and a passage go in with different prefixes - and making that the 
caller's job means the caller forgets. A missing prefix degrades retrival 
sitently, with no error anywhere."""

import hashlib
import json
import struct
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Protocol

from nbfc_ews.config import (
    AZURE_EMBED_DEPLOYMENT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
)

DIMENSIONS = 768

class EmbedderError(Exception):
    """The embedding service refused or misbehaved."""

class Embedder(Protocol):
    """Anything that can turn text into a vector. Reak or fake."""

    @property
    def name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_document(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

class AzureEmbedder:
    """test=embedding-3-small, via an azure OpenAI deployment.
    
    OpenAI's embedding model are symmetri - no query or document prefix - so
    both methods send the text unchanged. The two methods still exits because 
    the protocol required them and other implementations need them"""

    document_prefix = ""
    query_prefix = ""

    def __init__(
            self,
            endpoint: str = AZURE_OPENAI_ENDPOINT,
            api_key: str = AZURE_OPENAI_API_KEY,
            deployment: str = AZURE_EMBED_DEPLOYMENT,
            dimensions: int = DIMENSIONS,
            timeout: float = 60.0,
            api_version: str = "2024-02-01",
    ) -> None:

        if not endpoint or not api_key or not deployment:
            raise EmbedderError(
                "Azure embedding is not configured: set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY and AZURE_EMBED_DEPLOYMENT"
            )

        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._deployment = deployment
        self._dimensions = dimensions
        self._timeout = timeout
        self._api_version = api_version

    @property
    def name(self) -> str:
        return self._deployment

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed([self.document_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.query_prefix + text])[0]

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        payload = json.dumps(
            {
                "input": inputs,
                "dimensions": self._dimensions
            }
        ).encode()

        url = (
            f"{self._endpoint}/openai/deployments/{self._deployment}"
            f"/embeddings?api-version={self._api_version}"
        )

        request = urllib.request.Request(
            url=url, 
            data = payload,
            headers={
                "Content-Type": "application/json",
                "api-key": self._api_key,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise EmbedderError(f"Azure returned {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise EmbedderError(f"could not reach {self._endpoint}: {exc.reason}") from exc

        #Order is not guaranteed by the contract - sort by index the API
        #returns rather that trusting the order of the list.

        rows = sorted(body["data"], key = lambda row: row["index"])
        vectors = [row["embedding"] for row in rows]

        if len(vectors) != len(inputs):
            raise EmbedderError(
                f"asked for {len(inputs)} embeddungs, got {len(vectors)}"
            )
        for vector in vectors:
            if len(vector) != self._dimensions:
                raise EmbedderError(
                    f"{self._deployment} returned {len(vector)} dimensions, "
                    f"expected {self._dimensions}"
                )
        return vectors

class FakeEmbedder:
    """Deterministic vector from a hash, No Network, no Azure, no cost.
    
    Deliberately asymmetric - the two methods use different prefixes - so that
    a text can prove the document and query paths are actually distinct. Nothing
    here is semantically meaningful: it tests plumbing, not retrival quality."""

    document_prefix = "document: "
    query_prefix = "query: "

    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self._dimensions = dimensions

    @property
    def name(self) -> str:
            return "fake"

    @property
    def dimensions(self) -> int:
            return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(self.document_prefix + t)  for t in texts ]

    def embed_query(self, text:str) -> list[float]:
        return self._vector(self.query_prefix + text)

    def _vector(self, text: str) -> list[float]:
        out: list[float] = []
        counter = 0
        while len(out) < self._dimensions:
            digest = hashlib.sha256(f"{counter} : {text}".encode()).digest()
            for i in range(0, len(digest), 4):
                if len(out) == self._dimensions:
                    break
                (value,) = struct.unpack("<I", digest [i : i+4])
                out.append(value / 2** 31 - 1.0)
            counter += 1
        return out

            