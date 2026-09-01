import numpy as np

from modbot.spam_index import SpamIndex


def _unit(values):
    vector = np.array(values, dtype=np.float32)
    return vector / np.linalg.norm(vector)


def test_empty_index_has_zero_similarity():
    index = SpamIndex()
    assert len(index) == 0
    assert index.max_similarity(_unit([1, 0, 0])) == 0.0


def test_identical_vector_is_highly_similar():
    vector = _unit([1, 1, 0])
    index = SpamIndex([vector])
    assert index.max_similarity(vector) > 0.99


def test_orthogonal_vector_is_dissimilar():
    index = SpamIndex([_unit([1, 0, 0])])
    assert index.max_similarity(_unit([0, 1, 0])) < 0.01


def test_add_grows_the_index():
    index = SpamIndex()
    index.add(_unit([1, 0, 0]))
    index.add(_unit([0, 1, 0]))
    assert len(index) == 2


def test_best_match_returns_metadata():
    v1 = _unit([1, 0, 0])
    v2 = _unit([0, 1, 0])
    index = SpamIndex(
        [v1, v2],
        vector_ids=[101, 202],
        template_texts=["buy tickets now", "cheap electronics"],
    )
    match = index.best_match(_unit([0.95, 0.05, 0]))
    assert match.vector_id == 101
    assert "tickets" in match.template_text
    assert match.similarity > 0.9
