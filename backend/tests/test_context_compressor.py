from __future__ import annotations

from copy import deepcopy

import pytest
from backend.app.context_compressor import compress_contexts
from backend.app.domain import RetrievedChunk, TextChunk


def make_item(text: str, *, chunk_id: str = "chunk-1", score: float = 0.75) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=TextChunk(
            id=chunk_id,
            post_id="post-1",
            source="kumoh",
            title="수강신청 기간 안내",
            text=text,
            url="https://example.com/post-1",
            published_at="2026-02-11",
            chunk_index=2,
            topic_key="registration",
            topic_label="수강신청",
            is_latest_topic=True,
            intent_key="registration.main",
        ),
        score=score,
    )


def test_compresses_long_post_with_body_terms_and_excludes_header_scaffolding() -> None:
    item = make_item(
        "제목: 수강신청 기간 안내\n"
        "작성일: 2026-02-11\n"
        "본문: 학교 시설 이용 안내입니다.\n"
        "수강 신청 기간은 3월 1일부터 3월 5일까지입니다.\n"
        "신청 방법은 포털에서 진행합니다.\n"
        " unrelated archive text."
    )

    compressed = compress_contexts([item], terms=("수강신청 기간", "신청 방법"), max_sentences=2)

    assert compressed[0].chunk.text == (
        "수강 신청 기간은 3월 1일부터 3월 5일까지입니다.\n"
        "신청 방법은 포털에서 진행합니다."
    )
    assert "제목:" not in compressed[0].chunk.text
    assert "작성일:" not in compressed[0].chunk.text
    assert "학교 시설" not in compressed[0].chunk.text
    assert "unrelated" not in compressed[0].chunk.text


def test_compression_preserves_metadata_exactly_and_does_not_mutate_input() -> None:
    item = make_item("본문: 수강신청 기간은 3월입니다. 다른 내용입니다.")
    before = deepcopy(item)
    metadata_before = item.chunk.model_dump(exclude={"text"})

    compressed = compress_contexts([item], terms=("수강신청 기간",))

    assert compressed[0].chunk.model_dump(exclude={"text"}) == metadata_before
    assert compressed[0].score == item.score
    assert item == before
    assert item.chunk.text == "본문: 수강신청 기간은 3월입니다. 다른 내용입니다."


def test_no_valid_terms_no_body_or_no_match_returns_original_item_unchanged() -> None:
    no_terms = make_item("본문: 수강신청 기간입니다.")
    no_body = make_item("제목: 수강신청 기간 안내\n본문:")
    no_match = make_item("본문: 장학금 신청 안내입니다.")

    assert compress_contexts([no_terms], terms=("a", " ")) == [no_terms]
    assert compress_contexts([no_body], terms=("수강신청",)) == [no_body]
    result = compress_contexts([no_match], terms=("수강신청",))
    assert result == [no_match]
    assert result[0] is no_match


def test_splits_punctuation_and_lines_deduplicates_and_restores_original_order() -> None:
    item = make_item(
        "본문: 무관한 첫 문장. 수강신청 기간은 3월입니다!\n"
        "수강신청 기간은 3월입니다!\n무관한 마지막 문장?"
    )

    compressed = compress_contexts([item], terms=("수강 신청 기간",), max_sentences=3)

    assert compressed[0].chunk.text == "수강신청 기간은 3월입니다!"


def test_normalizes_punctuation_out_of_terms_and_matches_alphanumeric_text() -> None:
    item = make_item("본문: 수강 신청 기간은 3월입니다. 무관한 문장입니다.")

    compressed = compress_contexts(
        [item], terms=("수강-신청 기간!!!", "!!!"), max_sentences=1
    )

    assert compressed[0].chunk.text == "수강 신청 기간은 3월입니다."


def test_does_not_match_term_inside_an_alphanumeric_token() -> None:
    item = make_item("본문: 미채용 공고입니다. 채용 일정은 별도 안내합니다.")

    compressed = compress_contexts([item], terms=("채용",))

    assert compressed[0].chunk.text == "채용 일정은 별도 안내합니다."


def test_prefers_concise_sentence_when_term_coverage_ties() -> None:
    item = make_item(
        "본문: 장학금 신청 안내입니다.\n"
        "장학금 신청 안내이며 추가적인 세부 정보도 함께 확인할 수 있습니다."
    )

    compressed = compress_contexts(
        [item], terms=("장학금", "신청"), max_sentences=1
    )

    assert compressed[0].chunk.text == "장학금 신청 안내입니다."


@pytest.mark.parametrize("items", [None, "not-items", [object()], ["not-a-chunk"]])
def test_rejects_invalid_item_containers_or_members(items: object) -> None:
    with pytest.raises((TypeError, ValueError), match="items"):
        compress_contexts(items, terms=("수강신청",))  # type: ignore[arg-type]


def test_selected_sentences_are_original_substrings() -> None:
    item = make_item(
        "제목: 수강신청 안내\n"
        "작성일: 2026-02-11\n"
        "본문: 수강 신청 기간은 3월입니다. 신청 방법은 포털입니다."
    )

    compressed = compress_contexts(
        [item], terms=("수강신청", "신청 방법"), max_sentences=2
    )

    for sentence in compressed[0].chunk.text.splitlines():
        assert sentence in item.chunk.text


def test_max_sentences_limits_selection_and_validates_arguments() -> None:
    item = make_item(
        "본문: 수강신청 기간은 3월입니다. 신청 방법은 포털입니다. 등록금 납부 기간입니다."
    )

    compressed = compress_contexts(
        [item], terms=("수강신청", "신청 방법", "등록금"), max_sentences=1
    )
    assert compressed[0].chunk.text == "수강신청 기간은 3월입니다."

    with pytest.raises(ValueError, match="max_sentences"):
        compress_contexts([item], terms=("수강신청",), max_sentences=0)
    with pytest.raises(ValueError, match="max_sentences"):
        compress_contexts([item], terms=("수강신청",), max_sentences=True)  # type: ignore[arg-type]


@pytest.mark.parametrize("terms", ["수강신청", None, {"수강신청"}, ["수강신청", 1]])
def test_rejects_invalid_term_containers(terms: object) -> None:
    item = make_item("본문: 수강신청 기간입니다.")

    with pytest.raises((TypeError, ValueError), match="terms"):
        compress_contexts([item], terms=terms)  # type: ignore[arg-type]
