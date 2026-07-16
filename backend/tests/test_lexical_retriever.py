import math
from dataclasses import FrozenInstanceError

import backend.app.lexical_retriever as lexical_retriever
import pytest
from backend.app.domain import TextChunk
from backend.app.lexical_retriever import BM25Retriever, LexicalResult, _tokenize


def make_chunk(
    chunk_id: str,
    title: str,
    text: str,
    *,
    intent_key: str = "registration.main",
) -> TextChunk:
    return TextChunk(
        id=chunk_id,
        post_id=f"post-{chunk_id}",
        source="kumoh",
        title=title,
        text=text,
        url=f"https://kumoh.example/{chunk_id}",
        published_at="2026-07-16",
        chunk_index=0,
        topic_key="registration",
        topic_label="수강신청",
        is_latest_topic=True,
        intent_key=intent_key,
    )


def registration_chunk() -> TextChunk:
    return make_chunk(
        "registration-main",
        "2026학년도 수강신청 일정 안내",
        "최근 수강신청 기간과 신청 방법, 수강정정 일정을 안내합니다.",
    )


def attendance_chunk() -> TextChunk:
    return make_chunk(
        "registration-attendance",
        "2026 조기취업자 출석인정 신청 안내",
        "조기취업자의 출석인정 신청과 증빙서류 제출 방법을 안내합니다.",
        intent_key="registration.attendance",
    )


def test_exact_registration_main_ranks_above_newer_attendance_notice() -> None:
    retriever = BM25Retriever([attendance_chunk(), registration_chunk()])

    results = retriever.search(["최근 수강신청 공지"], top_k=2)

    assert results[0].chunk.intent_key == "registration.main"
    assert [result.rank for result in results] == [1, 2]


def test_result_preserves_chunk_metadata_and_has_frozen_contract() -> None:
    chunk = registration_chunk()
    result = BM25Retriever([chunk]).search(["수강신청"], top_k=1)[0]

    assert isinstance(result, LexicalResult)
    assert result.chunk is chunk
    assert result.chunk.model_dump() == chunk.model_dump()
    with pytest.raises(FrozenInstanceError):
        result.rank = 2  # type: ignore[misc]


def test_ranking_is_deterministic_by_score_then_chunk_id() -> None:
    first = make_chunk("b-id", "수강신청 공지", "수강신청 공지")
    second = make_chunk("a-id", "수강신청 공지", "수강신청 공지")
    retriever = BM25Retriever([first, second])

    first_run = retriever.search(["수강신청"], top_k=2)
    second_run = retriever.search(["수강신청"], top_k=2)

    assert [item.chunk.id for item in first_run] == ["a-id", "b-id"]
    assert first_run == second_run


def test_korean_spacing_matches_compact_form() -> None:
    spaced = make_chunk("spaced", "수강 신청 안내", "수강 신청 기간을 확인하세요.")
    unrelated = make_chunk(
        "unrelated",
        "장학금 신청 안내",
        "장학금 신청 기간입니다.",
        intent_key="scholarship.general",
    )

    results = BM25Retriever([unrelated, spaced]).search(["수강신청"], top_k=1)

    assert [result.chunk.id for result in results] == ["spaced"]


@pytest.mark.parametrize(
    ("chunk_title", "query"),
    [
        ("수강 신청 안내", "수강신청"),
        ("수강신청 안내", "수강 신청"),
    ],
)
def test_korean_spacing_matches_in_both_directions(
    chunk_title: str,
    query: str,
) -> None:
    chunk = make_chunk("spacing", chunk_title, "일정을 확인하세요.")

    results = BM25Retriever([chunk]).search([query], top_k=1)

    assert results[0].chunk is chunk


def test_tokenizer_normalizes_unicode_and_excludes_punctuation_and_underscore() -> None:
    features = set(_tokenize("ＡＢＣ_测试,ΔΕΛΤΑ!"))

    assert "abc" in features
    assert "测试" in features
    assert "δελτα" in features
    assert "abc_测试" not in features
    assert not any("_" in feature or any(char in ",!" for char in feature) for feature in features)


def test_non_ascii_cjk_text_matches() -> None:
    chunk = make_chunk("cjk", "课程申请指南", "提交课程申请的方法")

    results = BM25Retriever([chunk]).search(["课程申请"], top_k=1)

    assert results[0].chunk is chunk


def test_ngrams_do_not_span_more_than_one_word_boundary() -> None:
    three_single_character_words = set(_tokenize("a b c"))
    three_words_with_middle_length = set(_tokenize("a bb c"))

    assert "abc" not in three_single_character_words
    assert "abb" in three_words_with_middle_length
    assert "bbc" in three_words_with_middle_length
    assert "abbc" not in three_words_with_middle_length


def test_repeated_generic_query_features_do_not_amplify_ranking() -> None:
    generic = make_chunk("generic", "공지", "")
    specific = make_chunk("specific", "수강신청", "")
    retriever = BM25Retriever([generic, specific])

    baseline = retriever.search(["공지 수강신청"], top_k=2)
    repeated_generic = retriever.search(["공지 공지 공지 수강신청"], top_k=2)

    assert [item.chunk.id for item in repeated_generic] == [item.chunk.id for item in baseline]
    assert {
        item.chunk.id: item.score for item in repeated_generic
    } == pytest.approx({item.chunk.id: item.score for item in baseline})


def test_duplicate_chunk_ids_are_rejected() -> None:
    chunk = registration_chunk()

    with pytest.raises(ValueError, match=r"(?i)duplicate.*id|unique"):
        BM25Retriever([chunk, chunk])


def test_search_pre_tokenizes_each_unique_nonblank_query_variant_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retriever = BM25Retriever([registration_chunk(), attendance_chunk()])
    original_tokenize = lexical_retriever._tokenize
    calls: list[str] = []

    def tracked_tokenize(value: str) -> tuple[str, ...]:
        calls.append(value)
        return original_tokenize(value)

    monkeypatch.setattr(lexical_retriever, "_tokenize", tracked_tokenize)

    retriever.search(["수강신청", "", "수강신청", "출석"], top_k=2)

    assert calls == ["수강신청", "출석"]


@pytest.mark.parametrize(
    ("chunk_text", "query"),
    [
        ("공 지", "공지"),
        ("수 강 신 청", "강신청"),
        ("수 강 신 청", "수강신청"),
    ],
)
def test_compact_matching_supports_two_three_and_four_grams(
    chunk_text: str,
    query: str,
) -> None:
    chunk = make_chunk("compact", "분리된 한글", chunk_text)

    results = BM25Retriever([chunk]).search([query], top_k=1)

    assert results[0].chunk is chunk
    assert results[0].score > 0


def test_chunk_score_uses_maximum_across_query_variants() -> None:
    first = make_chunk("first", "희귀알파", "첫 번째 내용")
    second = make_chunk("second", "보통베타", "두 번째 내용")
    retriever = BM25Retriever([first, second])

    variants = ["희귀알파", "보통베타"]
    combined = {item.chunk.id: item.score for item in retriever.search(variants, top_k=2)}
    individual = {
        chunk.id: max(
            item.score
            for variant in variants
            for item in retriever.search([variant], top_k=2)
            if item.chunk.id == chunk.id
        )
        for chunk in (first, second)
    }

    assert combined == individual


def test_okapi_score_is_positive_and_matches_hand_checkable_formula() -> None:
    rare = make_chunk("rare", "희", "")
    other = make_chunk("other", "공", "")
    retriever = BM25Retriever([rare, other])

    result = retriever.search(["희"], top_k=1)[0]
    expected_idf = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
    expected_score = expected_idf * (1 * (1.5 + 1)) / (1 + 1.5 * (1 - 0.75 + 0.75))

    assert result.score > 0
    assert result.score == pytest.approx(expected_score)


@pytest.mark.parametrize(
    ("title", "text", "query"),
    [
        ("수강신청 제목", "일반적인 본문", "수강신청"),
        ("일반적인 제목", "수강신청 본문", "수강신청"),
    ],
)
def test_title_only_and_text_only_matching(
    title: str,
    text: str,
    query: str,
) -> None:
    chunk = make_chunk("field", title, text)

    results = BM25Retriever([chunk]).search([query], top_k=1)

    assert results[0].chunk is chunk


def test_nonempty_corpus_with_no_tokens_does_not_divide_by_zero() -> None:
    empty = make_chunk("empty", "", "")
    retriever = BM25Retriever([empty])

    assert retriever._avgdl == 0
    assert retriever.search(["수강신청"], top_k=1) == []


def test_search_ignores_blank_variants_and_excludes_zero_scores() -> None:
    chunk = registration_chunk()
    retriever = BM25Retriever([chunk])

    assert retriever.search(["", "   ", "수강신청"], top_k=1)[0].chunk is chunk
    assert retriever.search(["존재하지 않는 단어"], top_k=1) == []
    assert BM25Retriever([]).search(["수강신청"], top_k=1) == []
    assert retriever.search([], top_k=1) == []


@pytest.mark.parametrize("top_k", [0, -1, True])
def test_top_k_must_be_a_positive_integer(top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k"):
        BM25Retriever([registration_chunk()]).search(["수강신청"], top_k=top_k)
