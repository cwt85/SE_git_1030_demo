# 拾光｜校園活動報名

整合 `master` 的 Pro 版畫面與 `feat/event-database` 的 PostgreSQL 資料操作。

```text
main.py              FastAPI 啟動、頁面與錯誤處理
route/events.py      活動及報名 API、Pydantic 驗證
DB.py                PostgreSQL 連線、資料模型與交易
templates/index.html 公開與管理頁面
alembic/             資料庫結構版本
sql/                 初始建表與可選測試資料
```

## 啟動

需要 Python 3.10 以上與 PostgreSQL。以下在專案根目錄執行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

第一次使用時將 `.env.example` 複製為 `.env`，填寫本機資料庫設定與密碼；已有 `.env` 時保留原檔。

```powershell
Copy-Item .env.example .env
```

在 Adminer 建立 `event_registration` 資料庫。新資料庫執行：

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
```

這台開發電腦已建表並記錄初始版本，可直接啟動網站；不用重建資料表或重跑測試資料 SQL。

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- 公開活動與姓名名單：<http://127.0.0.1:8000/>
- 管理活動、完整名單與停止報名：<http://127.0.0.1:8000/admin>
- API 文件：<http://127.0.0.1:8000/docs>

頁面需由 FastAPI 提供，不能直接雙擊 HTML 或只用靜態網站伺服器。前端沒有 localStorage 報名備援；連線失敗會顯示錯誤並可重試，只有 API 接受報名才顯示成功。

## 功能

新增活動、搜尋與篩選、姓名與電話報名、公開/管理名單、人數統計、重複報名限制、手動停止及時間截止。
台灣手機 `0912-345-678`、全形數字及 `+886912345678` 統一格式，同一活動同名同電話回傳 409。其他國碼保留。
日期使用帶時區的 ISO 8601；公開名單只顯示姓名，管理名單含電話與報名時間。

依課程計畫，本版管理功能不要求登入，使用範圍為本機課程展示。
各組員的 `localhost` 是各自電腦，Git 不同步實際資料庫和密碼；可用 Alembic 與 SQL 檔各自建置。

## 驗證

```powershell
.venv\Scripts\python.exe -m pytest -q
```

測試以獨立 schema 和交易回滾驗證 PostgreSQL 與 API，不修改 public 的活動資料。
細節見 `docs/資料庫串接說明.md` 及 `docs/整合驗證紀錄.md`。
