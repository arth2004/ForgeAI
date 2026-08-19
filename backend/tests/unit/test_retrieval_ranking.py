from app.services.retrieval.hybrid import (
    extract_query_code_terms,
    is_implementation_query,
    python_cosine_distance,
)


def test_extract_query_code_terms():
    # 1. Stop words filtering & code terms extraction
    q1 = "Where is the Tree-sitter parser implemented?"
    terms1 = extract_query_code_terms(q1)
    assert "tree_sitter" in terms1 or "treesitter" in terms1
    assert "parser" in terms1
    assert "where" not in terms1
    assert "is" not in terms1
    assert "the" not in terms1
    assert "implemented" not in terms1

    # 2. Hyphen and underscore expansion
    q2 = "tree-sitter ast_parser chunking"
    terms2 = extract_query_code_terms(q2)
    assert "tree_sitter" in terms2 or "tree-sitter" in terms2
    assert "ast_parser" in terms2 or "ast-parser" in terms2

    # 3. Deduplication
    q3 = "auth authentication auth token jwt"
    terms3 = extract_query_code_terms(q3)
    assert len(terms3) == len(set(terms3))


def test_is_implementation_query():
    assert is_implementation_query("Where is GitHub authentication implemented?") is True
    assert is_implementation_query("Where are embeddings generated?") is True
    assert is_implementation_query("How does incremental indexing detect changed files?") is True
    assert is_implementation_query("Find the project deletion implementation") is True
    assert is_implementation_query("General system overview") is False


def test_python_cosine_distance():
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    # Identical vectors -> distance 0.0
    assert abs(python_cosine_distance(vec_a, vec_b)) < 1e-6

    # Orthogonal vectors -> distance 1.0
    vec_c = [0.0, 1.0, 0.0]
    assert abs(python_cosine_distance(vec_a, vec_c) - 1.0) < 1e-6

    # Opposite vectors -> distance 2.0
    vec_d = [-1.0, 0.0, 0.0]
    assert abs(python_cosine_distance(vec_a, vec_d) - 2.0) < 1e-6

    # Zero vectors -> distance 1.0
    vec_zero = [0.0, 0.0, 0.0]
    assert python_cosine_distance(vec_a, vec_zero) == 1.0
    assert python_cosine_distance(vec_zero, vec_zero) == 1.0

    # Scaled identical vectors -> distance 0.0
    vec_scaled = [3.0, 0.0, 0.0]
    assert abs(python_cosine_distance(vec_a, vec_scaled)) < 1e-6

    # Empty / mismatched length
    assert python_cosine_distance([], [1.0]) == 1.0
    assert python_cosine_distance([1.0, 2.0], [1.0]) == 1.0
    assert python_cosine_distance([], []) == 1.0
