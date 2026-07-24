from backend.app.crawling.semantic_dedup import remove_semantic_duplicates


def test_remove_semantic_duplicates_keeps_unique_context_and_drops_near_duplicate() -> None:
    introduction = (
        "전공소개\n"
        "소프트웨어 개발에 참여할 실천적인 프로그래머를 양성한다.\n"
        "다양한 프로그래밍 언어와 시스템 설계 역량을 기른다."
    )
    education_objectives = (
        "교육목표\n"
        "소프트웨어 개발에 참여할 실천적인 프로그래머 양성을 교육의 목표로 한다."
    )

    cleaned = remove_semantic_duplicates(introduction, (education_objectives,))

    assert "전공소개" in cleaned
    assert "프로그래밍 언어와 시스템 설계 역량" in cleaned
    assert "실천적인 프로그래머를 양성한다" not in cleaned


def test_remove_semantic_duplicates_keeps_short_section_headings() -> None:
    content = "전공소개\n소프트웨어 개발 역량을 기른다.\n전공소개"

    cleaned = remove_semantic_duplicates(content, ())

    assert cleaned.count("전공소개") == 2
