import pytest

from nbfc_ews.retrieval.embed import DIMENSIONS, FakeEmbedder


@pytest.fixture
def embedder():
    return FakeEmbedder()


def test_the_same_text_always_gives_the_same_vector(embedder):
    assert embedder.embed_query("field visit") == embedder.embed_query("field visit")


def test_documents_and_queries_take_different_paths(embedder):
    """The prefixes are the point. If these ever match, the split has collapsed."""
    document = embedder.embed_documents(["field visit"])[0]
    query = embedder.embed_query("field visit")
    assert document != query


def test_every_vector_has_the_declared_width(embedder):
    vectors = embedder.embed_documents(["one", "two", "three"])
    assert all(len(v) == embedder.dimensions for v in vectors)
    assert len(embedder.embed_query("x")) == embedder.dimensions


def test_no_texts_means_no_vectors(embedder):
    assert embedder.embed_documents([]) == []


def test_one_vector_per_text_in_order(embedder):
    vectors = embedder.embed_documents(["a", "b", "a"])
    assert len(vectors) == 3
    assert vectors[0] == vectors[2]
    assert vectors[0] != vectors[1]


def test_the_default_width_matches_the_column(embedder):
    """vector(768) in policy_chunk. If this changes, that migration changes too."""
    assert embedder.dimensions == DIMENSIONS == 768