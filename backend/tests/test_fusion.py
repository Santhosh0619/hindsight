import uuid

import pytest

from app.services.retrieval.fusion import reciprocal_rank_fusion


def test_single_list_score_is_monotonic_with_rank() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion({"vector": [a, b, c]}, k=60)

    assert scores[a] > scores[b] > scores[c]


def test_single_list_score_matches_the_documented_formula() -> None:
    a = uuid.uuid4()
    scores = reciprocal_rank_fusion({"vector": [a]}, k=60)

    assert scores[a] == pytest.approx(1 / 61)


def test_id_appearing_in_multiple_lists_sums_its_per_list_contributions() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion({"vector": [a, b], "keyword": [b, a]}, k=60)

    assert scores[a] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[b] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[a] == pytest.approx(scores[b])


def test_id_found_by_two_sources_outranks_an_id_found_by_only_one() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = reciprocal_rank_fusion({"vector": [a, b], "keyword": [a, c]}, k=60)

    assert scores[a] > scores[b]
    assert scores[a] > scores[c]


def test_empty_input_produces_empty_scores() -> None:
    assert reciprocal_rank_fusion({}, k=60) == {}
    assert reciprocal_rank_fusion({"vector": []}, k=60) == {}
