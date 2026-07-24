from __future__ import annotations

from urllib.parse import urlparse

DEPARTMENT_NOTICE_HOST = "cs.kumoh.ac.kr"
DEPARTMENT_NOTICE_PATH = "/cs/sub0601.do"
DEPARTMENT_SITE_PATH_PREFIX = "/cs/"
ALLOWED_DEPARTMENT_STATIC_PATHS = frozenset(
    {
        "/cs/sub0101.do",
        "/cs/sub0102.do",
        "/cs/sub0104.do",
        "/cs/sub0105_2.do",
        "/cs/sub0401.do",
        "/cs/sub0504.do",
    }
)
UNIVERSITY_ACADEMIC_GUIDANCE_HOSTS = frozenset(
    {"kumoh.ac.kr", "www.kumoh.ac.kr"}
)
UNIVERSITY_ACADEMIC_GUIDANCE_PATH_PREFIX = "/ko/sub06_01_"


def kumoh_collection_exclusion_reason(url: str) -> str | None:
    """Return the collection-policy reason when a Kumoh URL is prohibited."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    path = parsed.path.casefold()

    if hostname == DEPARTMENT_NOTICE_HOST and path == DEPARTMENT_NOTICE_PATH:
        return "학과 홈페이지 공지사항은 수집 정책상 제외됩니다."
    if (
        hostname == DEPARTMENT_NOTICE_HOST
        and path.startswith(DEPARTMENT_SITE_PATH_PREFIX)
        and path not in ALLOWED_DEPARTMENT_STATIC_PATHS
    ):
        return (
            "학과 사이트 수집 범위는 전공소개·교육목표·교육과정·졸업 후 진로·"
            "비식별 교수소개·동아리 소개만 허용됩니다."
        )
    if (
        hostname in UNIVERSITY_ACADEMIC_GUIDANCE_HOSTS
        and path.startswith(UNIVERSITY_ACADEMIC_GUIDANCE_PATH_PREFIX)
    ):
        return "금오공과대학교 학사안내 사이트는 수집 정책상 제외됩니다."
    return None


def ensure_kumoh_collection_allowed(url: str) -> None:
    if reason := kumoh_collection_exclusion_reason(url):
        raise ValueError(reason)
