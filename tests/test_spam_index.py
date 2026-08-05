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
