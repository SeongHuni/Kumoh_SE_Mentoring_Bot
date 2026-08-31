# 최종 발표 PPTX 생성기 (docs/PPT_핵심4부.md 기반, 13슬라이드)
#   python scripts/build-final-ppt.py
#
# 디자인 원칙: 글보다 숫자와 표. 한 슬라이드에 문장 3개 이상 안 쓴다.
# 설명은 발표자 노트에 넣고, 화면에는 결론과 핵심 수치만 남긴다.
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

OUT = os.path.join("docs", "SE챗봇_RAG_최종발표.pptx")

# ---- 팔레트 (2차 발표와 동일 톤 유지) ----
ACCENT = RGBColor(0x0E, 0x7C, 0x86)
ACCENT_L = RGBColor(0xDC, 0xED, 0xEE)
INK = RGBColor(0x16, 0x20, 0x1F)
MUTED = RGBColor(0x66, 0x74, 0x6F)
LINE = RGBColor(0xD6, 0xDE, 0xDE)
BG = RGBColor(0xFF, 0xFF, 0xFF)
PANEL = RGBColor(0xF2, 0xF5, 0xF5)
POS = RGBColor(0x2E, 0x7D, 0x5B)
NEG = RGBColor(0xAA, 0x40, 0x38)
WARN_BG = RGBColor(0xF6, 0xEB, 0xD2)
WARN_FG = RGBColor(0x8A, 0x62, 0x12)
UNSURE_BG = RGBColor(0xEC, 0xE6, 0xF4)
UNSURE_FG = RGBColor(0x5B, 0x3E, 0x8A)

FONT = "맑은 고딕"
MONO = "Consolas"

W, H = Inches(13.333), Inches(7.5)
M = Inches(0.75)
CONTENT_W = W - 2 * M


# ------------------------------------------------------------ 기본 도구
def set_font(run, size, bold=False, color=INK, name=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", name)


def textbox(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    return tf


def para(tf, text, size, bold=False, color=INK, space_after=6, first=False,
         name=FONT, align=PP_ALIGN.LEFT, line=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.space_after = Pt(space_after)
    if line:
        p.line_spacing = line
    run = p.add_run()
    run.text = text
    set_font(run, size, bold, color, name)
    return p


def rect(slide, x, y, w, h, fill=PANEL, line_color=None):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line_color:
        sh.line.color.rgb = line_color
        sh.line.width = Pt(1)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def oval(slide, x, y, d, fill=ACCENT):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def new_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def header(slide, eyebrow, title, n=None):
    tf = textbox(slide, M, Inches(0.42), CONTENT_W, Inches(0.3))
    para(tf, eyebrow, 13, True, ACCENT, 0, first=True)
    tf2 = textbox(slide, M, Inches(0.78), CONTENT_W, Inches(0.85))
    para(tf2, title, 28, True, INK, 0, first=True, line=1.15)
    rect(slide, M, Inches(1.62), Inches(1.1), Pt(3), ACCENT)
    if n is not None:
        tf3 = textbox(slide, W - M - Inches(0.6), H - Inches(0.5), Inches(0.6), Inches(0.3))
        para(tf3, f"{n:02d}", 11, False, LINE, 0, first=True, name=MONO, align=PP_ALIGN.RIGHT)


def bullets(slide, x, y, w, items, size=17, gap=11, marker_color=ACCENT):
    tf = textbox(slide, x, y, w, Inches(4))
    for i, item in enumerate(items):
        text, bold = item if isinstance(item, tuple) else (item, False)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        p.line_spacing = 1.25
        r1 = p.add_run(); r1.text = "•  "
        set_font(r1, size, False, marker_color)
        r2 = p.add_run(); r2.text = text
        set_font(r2, size, bold, INK if bold else MUTED)
    return tf


def table(slide, x, y, w, rows, col_w=None, size=14, header_bg=ACCENT,
          highlight=None, align_right_from=99, row_h=0.42, right_cols=None):
    nrow, ncol = len(rows), len(rows[0])
    h = Inches(row_h) * nrow
    shape = slide.shapes.add_table(nrow, ncol, x, y, w, h)
    tbl = shape.table
    if col_w:
        total = sum(col_w)
        for i, cw in enumerate(col_w):
            tbl.columns[i].width = Emu(int(w * cw / total))
    for r in range(nrow):
        tbl.rows[r].height = Inches(row_h)
        for c in range(ncol):
            cell = tbl.cell(r, c)
            cell.margin_left = Inches(0.12)
            cell.margin_right = Inches(0.12)
            cell.margin_top = Inches(0.04)
            cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            txt = str(rows[r][c])
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = header_bg
                color, bold = RGBColor(0xFF, 0xFF, 0xFF), True
            else:
                is_hl = highlight and (r - 1) in highlight
                cell.fill.fore_color.rgb = ACCENT_L if is_hl else BG
                bold = is_hl or c == 0
                color = INK
                if txt.startswith("+"):
                    color = POS
                elif txt.startswith("-") or txt.startswith("−"):
                    color = NEG
            tfc = cell.text_frame
            tfc.word_wrap = True
            p = tfc.paragraphs[0]
            is_right = (c in right_cols) if right_cols is not None else (c >= align_right_from)
            p.alignment = PP_ALIGN.RIGHT if is_right else PP_ALIGN.LEFT
            run = p.add_run()
            run.text = txt
            use_mono = is_right and r > 0 and any(ch.isdigit() for ch in txt)
            set_font(run, size, bold, color, MONO if use_mono else FONT)
    return tbl


def big_stat(slide, x, y, w, value, caption, color=ACCENT, vsize=46, h=1.5, bg=None):
    bg = bg or ACCENT_L
    rect(slide, x, y, w, Inches(h))
    slide.shapes[-1].fill.fore_color.rgb = bg
    tf = textbox(slide, x + Inches(0.28), y + Inches(0.16), w - Inches(0.56), Inches(0.75))
    para(tf, value, vsize, True, color, 2, first=True, name=MONO)
    tf2 = textbox(slide, x + Inches(0.28), y + Inches(h - 0.5), w - Inches(0.56), Inches(0.4))
    para(tf2, caption, 13, False, INK, 0, first=True, line=1.2)


def callout(slide, x, y, w, label, text, bg=WARN_BG, fg=WARN_FG, h=1.15):
    h = Inches(h)
    rect(slide, x, y, w, h, bg)
    rect(slide, x, y, Pt(4), h, fg)
    tf = textbox(slide, x + Inches(0.25), y + Inches(0.14), w - Inches(0.5), Inches(0.3))
    para(tf, label, 12, True, fg, 4, first=True)
    tf2 = textbox(slide, x + Inches(0.25), y + Inches(0.48), w - Inches(0.5), h - Inches(0.6))
    para(tf2, text, 15, False, INK, 0, first=True, line=1.2)


def flow_steps(slide, x, y, w, steps, h=1.3):
    """가로 흐름도: 박스 n개를 화살표로 잇는다. steps: (제목, 부제) 목록."""
    n = len(steps)
    gap = Inches(0.35)
    box_w = (w - gap * (n - 1)) / n
    for i, (title, sub) in enumerate(steps):
        bx = x + i * (box_w + gap)
        rect(slide, bx, y, box_w, Inches(h), ACCENT_L if i % 2 == 0 else PANEL)
        tf = textbox(slide, bx + Inches(0.15), y + Inches(0.16), box_w - Inches(0.3), Inches(h - 0.3),
                     anchor=MSO_ANCHOR.MIDDLE)
        para(tf, title, 15, True, INK, 4, first=True, align=PP_ALIGN.CENTER)
        if sub:
            para(tf, sub, 11, False, MUTED, 0, align=PP_ALIGN.CENTER, line=1.15)
        if i < n - 1:
            ar = textbox(slide, bx + box_w, y, gap, Inches(h), anchor=MSO_ANCHOR.MIDDLE)
            para(ar, "→", 18, True, MUTED, 0, first=True, align=PP_ALIGN.CENTER)


def step_timeline(slide, x, y, w, steps, highlight=None):
    """세로 스텝: (번호라벨, 한줄설명) 목록. highlight 인덱스는 강조 배경."""
    row_h = Inches(0.9)
    for i, (label, text) in enumerate(steps):
        ry = y + i * row_h
        is_hl = highlight is not None and i == highlight
        if is_hl:
            rect(slide, x, ry, w, row_h - Inches(0.08), ACCENT_L)
        d = Inches(0.5)
        oval(slide, x + Inches(0.12), ry + Inches(0.16), d, ACCENT if is_hl else MUTED)
        tf = textbox(slide, x + Inches(0.12), ry + Inches(0.16), d, d, anchor=MSO_ANCHOR.MIDDLE)
        para(tf, str(i + 1), 16, True, RGBColor(0xFF, 0xFF, 0xFF), 0, first=True, align=PP_ALIGN.CENTER)
        tf2 = textbox(slide, x + Inches(0.85), ry + Inches(0.06), w - Inches(1.0), row_h - Inches(0.15),
                      anchor=MSO_ANCHOR.MIDDLE)
        para(tf2, label, 14, True, ACCENT if is_hl else INK, 2, first=True)
        para(tf2, text, 13, False, MUTED, 0, line=1.2)


def cards(slide, x, y, w, h, items):
    """items: (태그, 제목, 부제, 결과, 결과색) 목록. 3~4개 가로 카드."""
    n = len(items)
    gap = Inches(0.25)
    cw = (w - gap * (n - 1)) / n
    for i, (tag, title, sub, result, rcolor) in enumerate(items):
        cx = x + i * (cw + gap)
        rect(slide, cx, y, cw, h, PANEL)
        rect(slide, cx, y, cw, Pt(4), rcolor)
        tf = textbox(slide, cx + Inches(0.22), y + Inches(0.22), cw - Inches(0.44), h - Inches(0.4))
        para(tf, tag, 11, True, MUTED, 6, first=True)
        para(tf, title, 20, True, INK, 6)
        if sub:
            para(tf, sub, 12, False, MUTED, 10, line=1.2)
        para(tf, result, 15, True, rcolor, 0)


def checklist(slide, x, y, w, items, size=16):
    tf = textbox(slide, x, y, w, Inches(2.4))
    for i, t in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(14)
        p.line_spacing = 1.25
        r1 = p.add_run(); r1.text = "✓  "
        set_font(r1, size, True, ACCENT)
        r2 = p.add_run(); r2.text = t
        set_font(r2, size, False, INK)


# ------------------------------------------------------------ 빌드
def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # ===== 0. 표지 =====
    s = new_slide(prs)
    rect(s, Inches(0), Inches(0), W, H, BG)
    rect(s, Inches(0), Inches(0), Inches(0.22), H, ACCENT)
    tf = textbox(s, Inches(1.2), Inches(2.0), Inches(10.5), Inches(0.4))
    para(tf, "26 여름 SIG · 최종 발표", 16, True, ACCENT, 0, first=True)
    tf = textbox(s, Inches(1.2), Inches(2.6), Inches(11), Inches(1.6))
    para(tf, "학과 챗봇 RAG", 44, True, INK, 6, first=True)
    para(tf, "시행착오로 보는 개발 과정", 26, False, MUTED, 0)
    rect(s, Inches(1.2), Inches(4.6), Inches(3.6), Pt(2), LINE)
    tf = textbox(s, Inches(1.2), Inches(4.8), Inches(10), Inches(0.4))
    para(tf, "금오공과대학교 컴퓨터공학부 소프트웨어전공 · 2026-09-01", 15, False, INK, 0, first=True)
    notes(s, "학과 공지와 강의 후기를 검색해서 답하는 챗봇을 만들었습니다. "
             "오늘은 결과보다 무엇을 시도했고, 무엇이 틀렸고, 어떻게 바로잡았는지를 중심으로 말씀드리겠습니다.")

    # ===== 1. RAG 개념 =====
    s = new_slide(prs)
    header(s, "1부 · RAG란", "모델의 기억이 아니라, 찾아준 문서로만 답한다", 1)
    flow_steps(s, M, Inches(2.1), CONTENT_W, [
        ("질문", "학생이 입력"),
        ("검색", "관련 문서 찾기"),
        ("+ 질문 전달", "LLM에게"),
        ("답변", "근거와 함께"),
    ], h=1.3)
    tf = textbox(s, M, Inches(3.75), CONTENT_W, Inches(0.4))
    para(tf, "일반 챗봇: 학습 데이터에 없으면 모른다고 하거나 지어낸다(할루시네이션)", 15, False, NEG, 0, first=True)

    steps4 = [
        ("데이터 준비", "공지·강의평·FAQ를 청크로 분할"),
        ("임베딩", "청크·질문을 숫자 벡터로 변환"),
        ("검색", "가장 가까운 청크를 벡터 DB에서 탐색"),
        ("생성", "청크를 근거로 LLM이 답변 작성"),
    ]
    cw = (CONTENT_W - Inches(0.3) * 3) / 4
    for i, (t, d) in enumerate(steps4):
        x = M + i * (cw + Inches(0.3))
        rect(s, x, Inches(4.5), cw, Inches(1.9), PANEL)
        rect(s, x, Inches(4.5), cw, Pt(4), ACCENT)
        tf = textbox(s, x + Inches(0.2), Inches(4.75), cw - Inches(0.4), Inches(1.5))
        para(tf, str(i + 1), 22, True, ACCENT, 6, first=True, name=MONO)
        para(tf, t, 16, True, INK, 6)
        para(tf, d, 12, False, MUTED, 0, line=1.25)
    notes(s, "답의 재료를 모델의 기억이 아니라 저희가 찾아준 문서로 제한하는 것이 핵심입니다. "
             "그래서 근거 없는 답을 지어낼 가능성이 줄고, 공지 하나만 추가하면 그날부터 최신 정보로 답할 수 있습니다.")

    # ===== 2. 데이터 =====
    s = new_slide(prs)
    header(s, "2부 · 데이터 · 환경", "4개 출처, 907개 문서", 2)
    rows = [
        ["출처", "문서 수", "특징"],
        ["se게시판", "664", "학과 공지"],
        ["에브리타임", "196", "강의평 · 실명 포함"],
        ["학사 FAQ", "40", "대학 홈페이지"],
        ["공식 사이트", "7", "학과 소개"],
    ]
    table(s, M, Inches(2.1), Inches(7.4), rows, col_w=[2.2, 1.3, 3.5], size=15, right_cols=[1])
    x2 = M + Inches(7.9)
    w2 = CONTENT_W - Inches(7.9)
    big_stat(s, x2, Inches(2.1), w2, "907", "문서")
    big_stat(s, x2, Inches(3.75), w2, "1,549", "검색 청크")
    notes(s, "학과 공지가 가장 많고, 강의평은 실명 교수명이 들어 있어 외부에 공개하지 않습니다.")

    # ===== 3. 개발 환경 =====
    s = new_slide(prs)
    header(s, "2부 · 데이터 · 환경", "무엇으로 만들었나", 3)
    chips = [
        ("백엔드", "Python 3.13\nFastAPI 0.139"),
        ("임베딩/생성", "text-embedding-3-small\ngpt-4o-mini"),
        ("벡터 DB", "Chroma 1.5.9\nHNSW · cosine"),
        ("프론트엔드", "Node 22\nNext.js 15.5 · React 19"),
        ("배포", "Docker Compose\n3개 컨테이너"),
    ]
    cw = (CONTENT_W - Inches(0.3) * 4) / 5
    for i, (t, d) in enumerate(chips):
        x = M + i * (cw + Inches(0.3))
        rect(s, x, Inches(2.3), cw, Inches(2.4), PANEL)
        rect(s, x, Inches(2.3), cw, Pt(4), ACCENT)
        tf = textbox(s, x + Inches(0.18), Inches(2.55), cw - Inches(0.36), Inches(2.0))
        para(tf, t, 15, True, INK, 10, first=True, line=1.2)
        para(tf, d, 12, False, MUTED, 0, line=1.35)
    notes(s, "비용 때문에 gpt-4o-mini를 골랐습니다. 검색이 정확하면 생성 모델의 부담이 줄어든다고 보고, "
             "시간을 검색 품질에 더 많이 썼습니다.")

    # ===== 4. 평가 원칙 =====
    s = new_slide(prs)
    header(s, "3부 · 청킹 · 오버랩 · 리랭킹", "수치를 보는 방법", 4)
    callout(s, M, Inches(2.3), CONTENT_W, "원칙 1 · 절대 수치를 주장하지 않는다",
            "평가 문항이 LLM 생성이라 편향이 있었다. 그래서 같은 평가셋으로 잰 상대 비교로만 쓴다.",
            bg=ACCENT_L, fg=ACCENT, h=1.3)
    callout(s, M, Inches(3.85), CONTENT_W, "원칙 2 · 숫자보다 확실한 증거",
            "실제로 챗봇을 돌려보는 시연이 어떤 표보다 신뢰할 수 있는 증거다.",
            bg=PANEL, fg=MUTED, h=1.3)
    notes(s, "이 뒤로 나오는 모든 수치는 절대적인 정확도가 아니라 이 방식이 저 방식보다 나았다는 비교입니다. "
             "이 점을 먼저 말씀드리고 싶었습니다.")

    # ===== 5. 청킹 =====
    s = new_slide(prs)
    header(s, "3부 · 청킹 · 오버랩 · 리랭킹", "청킹 — 500토큰 고정", 5)
    tf = textbox(s, M, Inches(2.05), Inches(7.0), Inches(0.4))
    para(tf, "18개 전략 비교 (크기 × 분할방식 × overlap × 헤더)", 15, False, MUTED, 0, first=True)
    rows = [
        ["실험", "Recall@3", "Recall@5"],
        ["D_500 (500토큰 고정)", "0.875", "0.912"],
        ["300토큰 고정", "0.800", "0.875"],
        ["재귀적 분할(500)", "0.838", "0.950"],
    ]
    table(s, M, Inches(2.55), Inches(7.4), rows, col_w=[3.2, 1.4, 1.4], size=15,
          align_right_from=1, highlight=[0])
    x2 = M + Inches(7.9)
    w2 = CONTENT_W - Inches(7.9)
    big_stat(s, x2, Inches(2.55), w2, "500", "토큰 고정 채택", vsize=52)
    tf = textbox(s, x2, Inches(4.3), w2, Inches(1.5))
    para(tf, "크기를 줄이면 문맥 부족,\n키우면 검색 정밀도 하락\n— 500이 균형점", 13, False, MUTED, 0, first=True, line=1.3)
    notes(s, "18개나 비교한 이유는 왜 500인가에 감으로 답하지 않기 위해서였습니다.")

    # ===== 6. 오버랩 =====
    s = new_slide(prs)
    header(s, "3부 · 청킹 · 오버랩 · 리랭킹", "오버랩 — 네 번의 반전 끝에 미사용", 6)
    step_timeline(s, M, Inches(2.05), Inches(7.3), [
        ("반전 1", "구현 버그로 적용률 15~30%뿐. 고쳐도 성능 그대로"),
        ("반전 2", "\"문서가 안 잘림\" 설명 오류 — 실제 41.6% 분할"),
        ("반전 3 · 핵심", "근거 문장이 경계에 걸린 경우 96건 중 1건"),
        ("반전 4", "\"헤더 효과\" 주장도 재현 안 돼 철회"),
    ], highlight=2)
    x2 = M + Inches(7.9)
    w2 = CONTENT_W - Inches(7.9)
    big_stat(s, x2, Inches(2.55), w2, "96건 중 1건", "경계에 걸린 근거 문장", vsize=30, bg=ACCENT_L, color=ACCENT)
    tf = textbox(s, x2, Inches(4.3), w2, Inches(1.6))
    para(tf, "overlap은 그 1건을\n100% 복구했다.\n효과가 없던 게 아니라\n기회가 없었을 뿐.", 13, False, MUTED, 0, first=True, line=1.3)
    notes(s, "공지문은 소설과 달리 문단이 서로 독립적이라, overlap이 필요한 상황 자체가 우리 데이터엔 거의 없었습니다.")

    # ===== 7. 리랭킹 =====
    s = new_slide(prs)
    header(s, "3부 · 청킹 · 오버랩 · 리랭킹", "리랭킹 — 미사용, 단 근거는 불완전", 7)
    tf = textbox(s, M, Inches(2.1), CONTENT_W, Inches(0.5))
    para(tf, "1차 검색 후보를 2차 모델로 재정렬 → 개선 미미, 지연 +2.2초", 16, False, MUTED, 0, first=True, line=1.3)
    bullets(s, M, Inches(2.9), Inches(7.2), [
        "실험 원본 데이터 유실 — 측정 문항 수 확인 불가",
        "입력 길이(max_length) 설정 오류 가능성 재검증 못함",
    ], size=16, gap=14)
    callout(s, M, Inches(4.7), CONTENT_W, "이 프로젝트에서 유일하게 확정되지 않은 결론",
            "근거 자료가 남아 있지 않아, 재검증 전까지는 \"현재 설정 기준\"이라는 단서를 붙인다.",
            bg=UNSURE_BG, fg=UNSURE_FG, h=1.25)
    notes(s, "솔직히 말씀드리면 이 프로젝트에서 유일하게 결론이 완전히 확정되지 않은 항목입니다.")

    # ===== 8. 3부 정리 =====
    s = new_slide(prs)
    header(s, "3부 · 정리", "최종 채택 — 청킹 500 / 오버랩 X / 리랭킹 X", 8)
    cards(s, M, Inches(2.3), CONTENT_W, Inches(3.0), [
        ("청킹", "500토큰", "18종 비교 중 Recall@3 최고", "채택", POS),
        ("오버랩", "미사용", "경계 걸림 96건 중 1건뿐", "미채택", NEG),
        ("리랭킹", "미사용", "개선 미미 + 지연 증가", "미채택 (재검증 필요)", UNSURE_FG),
    ])
    notes(s, "정리하면 이렇습니다. 셋 다 해봤는데 필요 없더라가 아니라, 각각 왜 필요 없었는지 데이터로 확인했다는 점이 다릅니다.")

    # ===== 9. 검색 정확도 =====
    s = new_slide(prs)
    header(s, "4부 · 검색정확도 · 프롬프트", "추측하지 않고 순위를 직접 찍어봤다", 9)
    rows = [
        ["증상", "원인", "조치"],
        ["장학금 검색 안 됨", "정답이 33위", "후보 100개로 확대"],
        ["\"MT\" 검색 실패", "다른 프로그램과 혼동", "소속 추가 +13%p"],
        ["분류 필터 위험", "틀리면 정답 통째 배제", "필터 제거"],
        ["옛 공지 우선 노출", "일상어 ≠ 공지 어투", "공지 어투로 변환"],
        ["학과명 붙여 실패", "소개 문서가 가림", "모호한 약어에만 적용"],
    ]
    table(s, M, Inches(2.1), CONTENT_W, rows, col_w=[2.6, 2.6, 2.6], size=14, row_h=0.62)
    notes(s, "다섯 가지 다 왜 안 되지를 추측 대신 실제 순위를 찍어서 찾은 원인입니다.")

    # ===== 10. 검색 계획기 =====
    s = new_slide(prs)
    header(s, "4부 · 검색정확도 · 프롬프트", "프롬프트 전략 — 검색 계획기", 10)
    flow_steps(s, M, Inches(2.1), CONTENT_W, [
        ("질문", ""),
        ("검색 계획기", "LLM이 재작성"),
        ("검색용 질의", "+ 대화 맥락"),
    ], h=1.2)
    rect(s, M, Inches(3.7), CONTENT_W, Inches(1.5), PANEL)
    tf = textbox(s, M + Inches(0.3), Inches(3.9), CONTENT_W - Inches(0.6), Inches(1.1))
    para(tf, "\"수강지도 상담은 언제야?\" → \"그럼 승인 안 되면?\"", 15, True, INK, 8, first=True, name=MONO)
    para(tf, "재작성: \"수강지도 상담 미승인 시 수강신청 제한\"", 15, False, ACCENT, 0, name=MONO)
    callout(s, M, Inches(5.5), CONTENT_W, "핵심 원칙",
            "이전 대화는 검색 대상을 정할 때만 쓰고, 사실의 근거로는 쓰지 않는다.",
            bg=ACCENT_L, fg=ACCENT, h=1.15)
    notes(s, "이전 대화 내용을 답의 근거로 써버리면, 대화가 길어질수록 오래된 정보를 사실인 것처럼 우길 위험이 있습니다.")

    # ===== 11. 답변 규칙 =====
    s = new_slide(prs)
    header(s, "4부 · 검색정확도 · 프롬프트", "답변 규칙 — 근거 없으면 답하지 않는다", 11)
    tf = textbox(s, M, Inches(2.1), CONTENT_W, Inches(0.5))
    para(tf, "규칙을 세게 걸었다가 → 답할 수 있는 질문도 거부 → 반례 추가로 균형", 16, False, MUTED, 0, first=True, line=1.3)
    cw = (CONTENT_W - Inches(0.4)) / 2
    big_stat(s, M, Inches(3.0), cw, "0", "환각 건수 (이전: 있었음)", color=POS, bg=ACCENT_L, vsize=54, h=2.0)
    big_stat(s, M + cw + Inches(0.4), Inches(3.0), cw, "0/14", "과잉거부 (이전: 5/12)", color=POS, bg=ACCENT_L, vsize=54, h=2.0)
    notes(s, "한쪽만 고치고 끝냈다면 반대쪽이 깨진 채로 넘어갈 뻔했습니다. "
             "고친 뒤엔 반드시 반대 방향도 재확인해야 한다는 걸 여기서 배웠습니다.")

    # ===== 12. 마무리 =====
    s = new_slide(prs)
    header(s, "마무리", "결과보다 과정", 12)
    checklist(s, M, Inches(2.3), CONTENT_W, [
        "기본이라고 알려진 것도 우리 데이터에서 직접 확인해야 한다",
        "한쪽을 고치면 반대쪽이 깨질 수 있다",
        "평가셋도 의심하고 검증해야 한다",
    ], size=19)
    tf = textbox(s, M, Inches(5.3), CONTENT_W, Inches(0.6))
    para(tf, "감사합니다.", 20, True, ACCENT, 0, first=True)
    notes(s, "오늘 보여드린 건 완성된 결과가 아니라, 저희가 세운 가설이 데이터 앞에서 어떻게 뒤집혔는지의 기록입니다.")

    os.makedirs("docs", exist_ok=True)
    prs.save(OUT)
    print(f"생성 완료: {OUT}")
    print(f"슬라이드 {len(prs.slides._sldIdLst)}장")


if __name__ == "__main__":
    build()
