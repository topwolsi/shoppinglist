"""쇼핑 리스트 데이터 저장/불러오기.

저장소를 외부 서비스(Google Sheets, Supabase 등)로 바꿀 때는
이 파일의 load_items() / update_items()만 교체하면 된다.
"""

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "items.json"

MAX_NAME_LEN = 50
MAX_QUANTITY = 999

# Streamlit은 모든 접속자 세션을 한 프로세스의 여러 스레드로 실행하므로
# 프로세스 내 잠금으로 동시 저장을 직렬화할 수 있다.
_lock = threading.RLock()
_recovered_files: list[Path] = []


def _normalize(raw: object, seen_ids: set[str]) -> dict | None:
    """파일에서 읽은 아이템 하나를 검증하고 빠진 값을 채운다. 쓸 수 없는 항목은 None."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        quantity = int(raw.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id or item_id in seen_ids:
        item_id = uuid.uuid4().hex
    seen_ids.add(item_id)
    return {
        "id": item_id,
        "name": name.strip()[:MAX_NAME_LEN],
        "quantity": min(max(quantity, 1), MAX_QUANTITY),
        "checked": bool(raw.get("checked", False)),
        "created_at": str(raw.get("created_at", "")),
    }


def _backup_broken_file() -> None:
    """깨진 데이터 파일을 덮어쓰지 않도록 다른 이름으로 옮겨 둔다."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATA_DIR / f"items.broken-{stamp}.json"
    DATA_FILE.replace(backup)
    _recovered_files.append(backup)


def load_items() -> list[dict]:
    """data/items.json에서 아이템 목록을 읽는다.

    - 파일이 없으면 빈 리스트
    - JSON이 깨졌거나 리스트가 아니면 파일을 백업하고 빈 리스트
    - 형식이 틀린 아이템은 고치거나 건너뛰고, 고친 내용은 바로 저장한다
    """
    with _lock:
        DATA_DIR.mkdir(exist_ok=True)
        if not DATA_FILE.exists():
            return []
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _backup_broken_file()
            return []
        except OSError:
            return []
        if not isinstance(data, list):
            _backup_broken_file()
            return []

        seen_ids: set[str] = set()
        items = [item for raw in data if (item := _normalize(raw, seen_ids)) is not None]
        if items != data:
            # 새로 만든 id가 실행할 때마다 바뀌지 않도록 정리된 내용을 저장해 둔다.
            save_items(items)
        return items


def save_items(items: list[dict]) -> None:
    """아이템 목록을 data/items.json에 저장한다."""
    with _lock:
        DATA_DIR.mkdir(exist_ok=True)
        # 고유한 임시 파일에 먼저 쓰고 교체해서, 저장 중 오류가 나도 기존 파일이 깨지지 않게 한다.
        tmp_file = DATA_DIR / f"items.{uuid.uuid4().hex}.tmp"
        tmp_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_file.replace(DATA_FILE)


def update_items(change: Callable[[list[dict]], list[dict] | None]) -> list[dict]:
    """최신 파일 내용을 읽어 change()로 고친 뒤 저장하고, 저장된 목록을 돌려준다.

    change()는 리스트를 직접 고치거나(None 반환) 새 리스트를 반환한다.
    여러 기기에서 동시에 써도 서로의 변경을 덮어쓰지 않게 하는 핵심 함수다.
    """
    with _lock:
        items = load_items()
        result = change(items)
        if result is not None:
            items = result
        save_items(items)
        return items


def pop_recovered_files() -> list[Path]:
    """깨진 파일을 백업한 경로를 꺼낸다 (화면에 한 번 안내하기 위해)."""
    with _lock:
        files = list(_recovered_files)
        _recovered_files.clear()
        return files
