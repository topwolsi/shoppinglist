# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Stages 1–4 of `PROMPTS.md` are done (skeleton, features F-01 ~ F-10, luxury-brand UI, Playwright review), and the bugs in `REVIEW.md` have been fixed. Next is stage 5 (deploy). Planning documents:
- `PRD.md` — the source of truth for requirements (feature IDs F-01 ~ F-11, data model, UI layout, deployment plan). Check work against it.
- `PROMPTS.md` — the staged development plan. Each stage has a defined scope; don't implement later-stage work early (e.g. stage 3 must not change feature logic, stage 4 reports bugs in `REVIEW.md` before fixing them).
- `REVIEW.md` — stage 4 findings (B1 ~ B8) and how each was fixed and verified; screenshots referenced there live in `review/`. `.playwright-mcp/` is Playwright scratch output (gitignored).

The user communicates in Korean; UI text, comments, and reports should be in Korean.

## Commands

```bash
pip install -r requirements.txt
streamlit run app.py
# headless, for Playwright review
streamlit run app.py --server.headless true --server.port 8501
```

There is no test suite in the repo; verification is done with `streamlit.testing.v1.AppTest` scripts and Playwright against a running server. `data/items.json` may contain the user's real list — back it up before any test that writes data, or run the test server from a copy of the app in another folder/port.

## Architecture

Streamlit shopping list app (add / edit / delete / check items), deployed to Streamlit Community Cloud.

- `storage.py` — the only place that touches `data/items.json`. `load_items()` validates/normalizes every item (fills missing keys, clamps quantity, re-ids duplicates and saves the fix so ids stay stable) and moves a corrupt file to `items.broken-<time>.json` (surfaced once via `pop_recovered_files()`). `update_items(change)` does read-modify-write under a process-wide `RLock` (all Streamlit sessions are threads in one process). Swap this file to change the backend.
- `app.py` — `init_state()` reloads items from the file on **every** run, and every mutation goes through `mutate(change)` → `update_items`. Never save a session's copy of the list wholesale: that was bug B1 (two tabs/devices overwrote each other).
- Callbacks run before the script body and, on rapid double submits, can see stale `session_state`; anything that must be current inside a callback (e.g. `just_added()`) reads the file, not the session.
- Item model: `{id (uuid str), name (≤50), quantity (1~999), checked (bool), created_at (ISO, KST +09:00)}`. Dates use the fixed `KST` timezone because the Cloud server runs in UTC.

Key constraints:
- Widget keys must be derived from item `id` (e.g. `f"check_{id}"`), never list index. Checkbox state is re-synced from the file each run (`st.session_state[f"check_{id}"] = item["checked"]` before rendering, no `value=`), and `set_checked()` writes the widget's value rather than flipping.
- Quantity inputs are `st.text_input` + `parse_quantity()`, not `st.number_input`: inside a form, Enter in a number input submits before the typed value is committed (verified in Streamlit 1.58).
- The edit row is its own `st.form` so Enter saves (first submit button = 저장).
- Names: strip whitespace, reject empty, max 50 chars; duplicates allowed with a toast. "Clear all" requires a confirm step (`confirm_clear` resets when the list empties).
- `data/` is gitignored. On Streamlit Cloud the file is ephemeral and shared by all visitors — accepted for v1.
- Styling: colors/radius come from `.streamlit/config.toml` (`[theme.light]` / `[theme.dark]`, restart the server after editing it); fonts, hairlines and mobile fixes are in the `CSS` string in `app.py`, scoped through keyed containers (`st.container(key="item_list")` → `.st-key-item_list`). Per-item widgets are addressable as `.st-key-check_<id>`, `.st-key-edit_<id>`, `.st-key-delete_<id>` (useful for Playwright).
- Layout must work at 360px width (CSS keeps `st.columns` rows horizontal, edit/delete touch targets ≥ 44px) and in both light and dark themes.
