# 🛒 쇼핑 리스트

아이템 추가, 수정, 삭제, 체크 기능이 있는 가벼운 쇼핑 리스트 웹 앱입니다. (Streamlit)

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 http://localhost:8501 로 접속합니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 메인 앱 (화면, 상태 관리, 기능) |
| `storage.py` | 데이터 불러오기/저장 (`data/items.json`) |
| `requirements.txt` | 필요한 패키지 |

요구사항은 `PRD.md`를 참고하세요.
