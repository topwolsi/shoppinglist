"""쇼핑 리스트 Streamlit 앱."""

import re
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st

from storage import MAX_NAME_LEN, MAX_QUANTITY, load_items, pop_recovered_files, update_items

# 배포 서버(Streamlit Cloud)는 UTC라서 날짜는 한국 시간 기준으로 계산한다.
KST = timezone(timedelta(hours=9), "KST")
# 추가 버튼을 빠르게 두 번 눌러 생긴 빈 제출은 경고 없이 무시한다.
# (두 제출이 같은 세션 상태로 처리되므로 세션 대신 파일에 저장된 마지막 추가 시각으로 판단한다)
DOUBLE_SUBMIT_SEC = 2
QUANTITY_ERROR = f"수량은 1~{MAX_QUANTITY} 사이의 숫자로 입력해 주세요."


# ---------- 상태 초기화 ----------

def init_state() -> None:
    """화면 상태를 초기화하고, 매 실행마다 파일에서 최신 아이템을 읽는다.

    다른 탭/기기에서 바꾼 내용이 다음 조작 때 바로 보이도록 세션에 사본을 오래 들고 있지 않는다.
    """
    st.session_state["items"] = load_items()
    st.session_state.setdefault("editing_id", None)
    st.session_state.setdefault("confirm_clear", False)
    st.session_state.setdefault("message", None)  # 다음 화면에 보여줄 경고 문구


def items() -> list[dict]:
    return st.session_state["items"]


def mutate(change) -> None:
    """최신 파일 기준으로 변경을 적용·저장하고 세션 목록을 갱신한다 (F-06)."""
    st.session_state["items"] = update_items(change)


def find_item(item_id: str) -> dict | None:
    return next((item for item in items() if item["id"] == item_id), None)


def clean_name(name: str) -> str:
    return (name or "").strip()[:MAX_NAME_LEN]


def parse_quantity(text) -> int | None:
    """수량 입력값을 정수로 바꾼다. 숫자가 아니거나 범위를 벗어나면 None."""
    try:
        quantity = int(str(text).strip())
    except ValueError:
        return None
    return quantity if 1 <= quantity <= MAX_QUANTITY else None


def just_added() -> bool:
    """방금(DOUBLE_SUBMIT_SEC 이내) 아이템이 추가됐는지. 세션 사본이 아니라 파일을 직접 본다."""
    saved = load_items()
    if not saved:
        return False
    try:
        last = datetime.fromisoformat(saved[-1]["created_at"])
    except ValueError:
        return False
    return last.tzinfo is not None and (datetime.now(KST) - last).total_seconds() < DOUBLE_SUBMIT_SEC


def escape_md(text: str) -> str:
    """사용자 입력이 마크다운 서식으로 해석되지 않게 특수문자를 이스케이프한다."""
    return re.sub(r"([\\`*_{}\[\]()<>#+\-.!|~:$])", r"\\\1", text)


# ---------- 기능 함수 ----------

def add_item(name: str, quantity="1") -> None:
    """아이템 추가 (F-01). 빈 이름이나 잘못된 수량은 추가하지 않는다."""
    name = clean_name(name)
    if not name:
        if not just_added():
            st.session_state["message"] = "아이템 이름을 입력해 주세요."
        return
    qty = parse_quantity(quantity)
    if qty is None:
        st.session_state["message"] = QUANTITY_ERROR
        return
    new_item = {
        "id": uuid.uuid4().hex,
        "name": name,
        "quantity": qty,
        "checked": False,
        "created_at": datetime.now(KST).isoformat(timespec="seconds"),
    }
    duplicate = False

    def change(current: list[dict]) -> None:
        nonlocal duplicate
        duplicate = any(item["name"].lower() == name.lower() for item in current)
        current.append(new_item)

    mutate(change)
    if duplicate:
        st.toast(f"이미 있는 아이템입니다: {name}")


def update_item(item_id: str, name: str, quantity) -> None:
    """아이템 이름/수량 수정 (F-02). 빈 이름이나 잘못된 수량이면 수정 모드를 유지한다."""
    name = clean_name(name)
    if not name:
        st.session_state["message"] = "빈 이름으로는 저장할 수 없습니다."
        return
    qty = parse_quantity(quantity)
    if qty is None:
        st.session_state["message"] = QUANTITY_ERROR
        return
    found = False

    def change(current: list[dict]) -> None:
        nonlocal found
        for item in current:
            if item["id"] == item_id:
                item["name"] = name
                item["quantity"] = qty
                found = True

    mutate(change)
    st.session_state["editing_id"] = None
    if not found:
        st.session_state["message"] = "다른 기기에서 이미 삭제된 아이템입니다."


def delete_item(item_id: str) -> None:
    """아이템 삭제 (F-03)."""
    mutate(lambda current: [item for item in current if item["id"] != item_id])
    if st.session_state["editing_id"] == item_id:
        st.session_state["editing_id"] = None


def set_checked(item_id: str, checked: bool) -> None:
    """아이템 체크/해제 (F-04). 뒤집지 않고 화면의 값으로 맞춰서 다른 기기 변경과 엇갈리지 않게 한다."""

    def change(current: list[dict]) -> None:
        for item in current:
            if item["id"] == item_id:
                item["checked"] = checked

    mutate(change)


def clear_checked() -> None:
    """체크된 아이템 일괄 삭제 (F-08)."""
    mutate(lambda current: [item for item in current if not item["checked"]])
    if find_item(st.session_state["editing_id"] or "") is None:
        st.session_state["editing_id"] = None


def clear_all() -> None:
    """전체 삭제 (F-09). 확인 단계를 거친 뒤 호출된다."""
    mutate(lambda current: [])
    st.session_state["editing_id"] = None
    st.session_state["confirm_clear"] = False


# ---------- 위젯 콜백 ----------

def on_add_submit() -> None:
    add_item(st.session_state["new_name"], st.session_state["new_qty"])


def on_toggle(item_id: str) -> None:
    set_checked(item_id, st.session_state[f"check_{item_id}"])


def on_start_edit(item_id: str) -> None:
    item = find_item(item_id)
    if item is None:
        return
    # 수정 입력창의 초기값을 현재 값으로 채운다 (위젯이 그려지기 전이라 설정 가능).
    st.session_state[f"edit_name_{item_id}"] = item["name"]
    st.session_state[f"edit_qty_{item_id}"] = str(item["quantity"])
    st.session_state["editing_id"] = item_id


def on_save_edit(item_id: str) -> None:
    update_item(
        item_id,
        st.session_state[f"edit_name_{item_id}"],
        st.session_state[f"edit_qty_{item_id}"],
    )


def on_cancel_edit() -> None:
    st.session_state["editing_id"] = None


def set_confirm_clear(value: bool) -> None:
    st.session_state["confirm_clear"] = value


# ---------- 화면 ----------

# 기본 색(배경·글자·버튼)은 .streamlit/config.toml의 라이트/다크 테마에서 정하고,
# 여기서는 두 테마 모두에 어울리는 골드 포인트와 반투명 회색 선만 쓴다.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=Noto+Serif+KR:wght@300;400;500&display=swap');

:root { --gold: #B08D57; --hairline: rgba(128, 128, 128, 0.28); }

/* 전체 타이포그래피: 세리프 + 넓은 자간 */
.stApp p, .stApp label, .stApp input, .stApp button, .stApp li,
.stApp [data-testid="stMarkdownContainer"] {
    font-family: 'Noto Serif KR', 'Cormorant Garamond', serif;
    font-weight: 300;
    letter-spacing: 0.02em;
}
.block-container { padding-top: 4.5rem; padding-bottom: 5rem; max-width: 620px; }

/* 헤더 */
.lux-header { text-align: center; margin-bottom: 2.5rem; }
.lux-eyebrow {
    font-family: 'Cormorant Garamond', serif; font-size: 0.72rem; font-weight: 500;
    letter-spacing: 0.45em; text-transform: uppercase; color: var(--gold);
}
.lux-title {
    font-family: 'Cormorant Garamond', serif; font-weight: 300; font-size: 3.6rem;
    line-height: 1.05; letter-spacing: 0.04em; margin: 0.9rem 0 0.6rem;
}
.lux-subtitle {
    font-family: 'Noto Serif KR', serif; font-size: 0.78rem; font-weight: 300;
    letter-spacing: 0.2em; opacity: 0.6;
}
.lux-rule { width: 48px; height: 1px; background: var(--gold); margin: 1.6rem auto 0; }

/* 작은 대문자 라벨 (입력 라벨, 진행 현황, 토글) */
.stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stProgress"] p {
    font-size: 0.7rem !important; letter-spacing: 0.16em; text-transform: uppercase; opacity: 0.7;
}
.stApp [data-testid="stProgress"] > div > div > div { height: 2px !important; }

/* 입력창: 배경 없이 밑줄만 */
.st-key-add_row [data-baseweb="input"], .st-key-add_row [data-baseweb="base-input"],
.st-key-item_list [data-baseweb="input"], .st-key-item_list [data-baseweb="base-input"] {
    background: transparent !important;
    border: none !important; border-bottom: 1px solid var(--hairline) !important;
}
.st-key-add_row input, .st-key-item_list input { background: transparent !important; }

/* 버튼: 대문자 자간, 각진 모서리 */
.stApp button p { font-size: 0.76rem !important; letter-spacing: 0.18em; font-weight: 400; }
.stApp button[kind="secondary"] { background: transparent; border-color: var(--hairline); }
.stApp button[kind="primaryFormSubmit"], .stApp button[kind="primary"] { min-height: 2.6rem; }

/* 아이템 목록: 위아래 가는 선, 줄 사이 구분선 */
.st-key-item_list {
    gap: 0; border-top: 1px solid var(--hairline); border-bottom: 1px solid var(--hairline);
    margin-top: 0.5rem;
}
.st-key-item_list [data-testid="stHorizontalBlock"] { padding: 0.95rem 0; }
.st-key-item_list [data-testid="stLayoutWrapper"] + [data-testid="stLayoutWrapper"] {
    border-top: 1px solid var(--hairline);
}
.st-key-item_list [data-testid="stCheckbox"] label { word-break: break-all; }
.stApp .st-key-item_list [data-testid="stCheckbox"] p {
    font-size: 1.02rem !important; font-weight: 400; letter-spacing: 0.03em;
    text-transform: none; opacity: 1;
}
.stApp .st-key-item_list [data-testid="stCheckbox"]:has(input:checked) p { opacity: 0.45; }

/* 수정/삭제: 작은 텍스트 링크 */
.st-key-item_list [data-testid="stColumn"]:not(:first-child) [data-testid="stButton"] {
    display: flex; justify-content: flex-end;
}
.st-key-item_list button[kind^="tertiary"] { min-height: 1.8rem; padding: 0 0.2rem; opacity: 0.5; }
.st-key-item_list button[kind^="tertiary"]:hover { opacity: 1; color: var(--gold); }
.st-key-item_list button[kind^="tertiary"] p { font-size: 0.7rem !important; letter-spacing: 0.12em; }
.st-key-item_list [data-testid="stForm"] { padding: 0; border: none; }

/* 빈 리스트 */
.lux-empty { text-align: center; padding: 3rem 0; border-top: 1px solid var(--hairline);
    border-bottom: 1px solid var(--hairline); }
.lux-empty em { font-family: 'Cormorant Garamond', serif; font-size: 1.5rem; font-weight: 300; }
.lux-empty div { font-size: 0.75rem; letter-spacing: 0.15em; opacity: 0.6; margin-top: 0.5rem; }

/* 경고 문구: 색 배경 대신 가는 골드 테두리 */
.stApp [data-testid="stAlertContainer"] {
    background: transparent !important; border: 1px solid var(--gold); color: inherit !important;
}
.stApp [data-testid="stAlertContainer"] p { font-size: 0.85rem; letter-spacing: 0.05em; }

.st-key-bulk_actions { margin-top: 1.5rem; }
.lux-footer { text-align: center; margin-top: 3.5rem; font-family: 'Cormorant Garamond', serif;
    font-size: 0.7rem; letter-spacing: 0.4em; text-transform: uppercase; opacity: 0.4; }

/* 모바일: st.columns가 세로로 쌓이지 않고 한 줄을 유지하게 한다 */
@media (max-width: 640px) {
    /* 손가락으로 누르기 쉽게 수정/삭제 버튼 터치 영역을 44px 이상으로 */
    .st-key-item_list button[kind^="tertiary"] { min-height: 2.75rem; padding: 0 0.15rem; }
    .st-key-item_list button[kind^="tertiary"] p { white-space: nowrap; letter-spacing: 0.05em; }
    .st-key-item_list [data-testid="stHorizontalBlock"] { padding: 0.4rem 0; }
    .st-key-add_row [data-testid="stHorizontalBlock"],
    .st-key-item_list [data-testid="stHorizontalBlock"],
    .st-key-bulk_actions [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 0.5rem;
    }
    .st-key-add_row [data-testid="stColumn"],
    .st-key-item_list [data-testid="stColumn"],
    .st-key-bulk_actions [data-testid="stColumn"] {
        min-width: 0 !important;
    }
    /* 추가 버튼 열은 글자 폭만큼 확보해서 "추가"가 세로로 꺾이지 않게 한다 */
    .st-key-add_row [data-testid="stColumn"]:last-child {
        flex: 0 0 auto !important; width: auto !important; min-width: 3.5rem !important;
    }
    .st-key-add_row button { white-space: nowrap; }
    .block-container { padding: 2.5rem 1rem 3rem; }
    .lux-title { font-size: 2.6rem; }
    .lux-eyebrow { letter-spacing: 0.35em; }
}
</style>
"""


def render_header() -> None:
    """브랜드 홈페이지 스타일 헤더 (고정 문구만 사용)."""
    today = datetime.now(KST).strftime("%A, %d %B %Y")
    st.markdown(
        f"""
        <div class="lux-header">
            <div class="lux-eyebrow">The Shopping Edit</div>
            <div class="lux-title">Shopping List</div>
            <div class="lux-subtitle">쇼핑 리스트 · {today}</div>
            <div class="lux-rule"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_progress() -> None:
    """진행 현황 (F-07)."""
    total = len(items())
    done = sum(item["checked"] for item in items())
    ratio = done / total if total else 0.0
    st.progress(ratio, text=f"전체 {total}개 중 {done}개 완료 ({ratio:.0%})")


def render_input_form() -> None:
    """아이템 입력 폼 (F-01, F-10): [이름] [수량] [추가] 한 줄 배치."""
    with st.form("add_form", clear_on_submit=True, border=False):
        with st.container(key="add_row"):
            col_name, col_qty, col_add = st.columns([5, 2, 1.3], vertical_alignment="bottom")
            col_name.text_input(
                "아이템 이름", key="new_name", placeholder="예: 우유", max_chars=MAX_NAME_LEN
            )
            # number_input은 폼 안에서 Enter를 누르면 입력한 값이 반영되기 전에 제출되므로 text_input을 쓴다.
            col_qty.text_input("수량", key="new_qty", value="1", max_chars=len(str(MAX_QUANTITY)))
            col_add.form_submit_button("추가", on_click=on_add_submit, type="primary", width="stretch")

    if st.session_state["message"]:
        st.warning(st.session_state["message"])
        st.session_state["message"] = None


def item_label(item: dict) -> str:
    label = f"{escape_md(item['name'])}  :gray[× {item['quantity']}]"
    return f":gray[~~{escape_md(item['name'])} × {item['quantity']}~~]" if item["checked"] else label


def render_edit_row(item: dict) -> None:
    """수정 모드 줄 (F-02)."""
    item_id = item["id"]
    # 폼으로 감싸서 입력창에서 Enter를 누르면 첫 번째 제출 버튼(저장)이 눌린 것과 같게 한다.
    with st.form(f"edit_form_{item_id}", border=False):
        col_name, col_qty, col_save, col_cancel = st.columns([4, 2, 1, 1], vertical_alignment="center")
        col_name.text_input(
            "이름", key=f"edit_name_{item_id}", max_chars=MAX_NAME_LEN, label_visibility="collapsed"
        )
        col_qty.text_input(
            "수량", key=f"edit_qty_{item_id}", max_chars=len(str(MAX_QUANTITY)), label_visibility="collapsed"
        )
        col_save.form_submit_button(
            "저장", key=f"save_{item_id}", on_click=on_save_edit, args=(item_id,), type="tertiary"
        )
        col_cancel.form_submit_button("취소", key=f"cancel_{item_id}", on_click=on_cancel_edit, type="tertiary")


def render_view_row(item: dict) -> None:
    """일반 모드 줄: 체크박스 + 수정/삭제 버튼 (F-03, F-04)."""
    item_id = item["id"]
    # 다른 기기에서 바뀐 체크 상태가 보이도록 위젯 상태를 매번 파일 값으로 맞춘다.
    st.session_state[f"check_{item_id}"] = item["checked"]
    col_check, col_edit, col_delete = st.columns([6, 1, 1], vertical_alignment="center")
    col_check.checkbox(
        item_label(item),
        key=f"check_{item_id}",
        on_change=on_toggle,
        args=(item_id,),
    )
    col_edit.button("수정", key=f"edit_{item_id}", on_click=on_start_edit, args=(item_id,), type="tertiary")
    col_delete.button("삭제", key=f"delete_{item_id}", on_click=delete_item, args=(item_id,), type="tertiary")


def render_item_list() -> None:
    """아이템 목록 표시 (F-05). 추가한 순서대로 보여준다."""
    if not items():
        st.markdown(
            '<div class="lux-empty"><em>Your list awaits.</em>'
            "<div>리스트가 비어 있습니다</div></div>",
            unsafe_allow_html=True,
        )
        return

    hide_checked = st.toggle("완료된 항목 숨기기", key="hide_checked")
    visible = [item for item in items() if not (hide_checked and item["checked"])]

    with st.container(key="item_list"):
        if not visible:
            st.caption("모든 아이템을 구매했습니다")
        for item in visible:
            if item["id"] == st.session_state["editing_id"]:
                render_edit_row(item)
            else:
                render_view_row(item)


def render_bulk_actions() -> None:
    """완료 항목 삭제 (F-08), 전체 삭제 (F-09)."""
    if not items():
        # 확인창을 연 채 리스트가 비면, 나중에 아이템을 추가했을 때 확인창이 다시 뜨지 않게 한다.
        st.session_state["confirm_clear"] = False
        return
    with st.container(key="bulk_actions"):
        if st.session_state["confirm_clear"]:
            st.warning("정말 전체 아이템을 삭제할까요? 되돌릴 수 없습니다.")
            col_yes, col_no = st.columns(2)
            col_yes.button("확인", key="clear_all_yes", on_click=clear_all, type="primary", width="stretch")
            col_no.button("취소", key="clear_all_no", on_click=set_confirm_clear, args=(False,), width="stretch")
            return
        has_checked = any(item["checked"] for item in items())
        col_checked, col_all = st.columns(2)
        col_checked.button("완료 항목 삭제", on_click=clear_checked, disabled=not has_checked, width="stretch")
        col_all.button("전체 삭제", on_click=set_confirm_clear, args=(True,), width="stretch")


def main() -> None:
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)

    render_header()
    for backup in pop_recovered_files():
        st.warning(f"데이터 파일이 손상되어 `{backup.name}`으로 백업하고 빈 리스트로 시작했습니다.")
    render_progress()
    render_input_form()
    render_item_list()
    render_bulk_actions()
    st.markdown('<div class="lux-footer">Curated with care</div>', unsafe_allow_html=True)


main()
