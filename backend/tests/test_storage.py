from backend.app.domain import BoardPost
from backend.app.storage import deduplicate_posts, load_posts, save_posts


def test_save_and_load_deduplicates_posts(tmp_path) -> None:
    post = BoardPost(
        id="1",
        source="seboard",
        title="취업 특강",
        content="취업 특강 신청 안내입니다.",
        url="https://seboard.site/posts/1",
    )
    path = tmp_path / "posts.json"

    save_posts([post, post], path)
    loaded = load_posts(path)

    assert len(deduplicate_posts([post, post])) == 1
    assert len(loaded) == 1
    assert loaded[0].title == "취업 특강"


def test_save_and_load_preserves_llm_category(tmp_path) -> None:
    post = BoardPost(
        id="llm-category",
        source="seboard",
        title="방산AI 과정 안내",
        content="비교과 행사 안내입니다.",
        url="https://seboard.site/notice/llm-category",
        llm_category="비교과·행사",
    )
    path = tmp_path / "posts.json"

    save_posts([post], path)
    loaded = load_posts(path)

    assert loaded[0].llm_category == "비교과·행사"
