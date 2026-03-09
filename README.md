# 邊坡災害通報與資訊整合管理系統

> Slope Disaster Reporting & Information Integration Management System  
> Phase 1 — Vibe Coding

交通部公路局北區養護工程分局

## 快速開始

```bash
# 1. 建立虛擬環境
python -m venv venv
venv\Scripts\activate  # Windows

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 複製環境變數
copy .env.example .env
copy secrets.private.env.example secrets.private.env
# 編輯 secrets.private.env 填入 LINE/ngrok/API 金鑰
# .env 放非機敏設定；secrets.private.env 放機敏設定

# 4. 啟動開發伺服器
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 系統架構

```
app/
├── core/          # 設定、日誌、安全模組
├── models/        # Pydantic 資料模型
├── routers/       # FastAPI 路由 (LINE webhook, cases, vendor API, health, webgis)
├── services/      # 業務邏輯 (案件管理, LINE 流程, LRS, 影像處理, PDF解析)
└── data/          # 靜態資料 (工務段, 照片標籤, 破壞模式, 里程樁號CSV)

storage/
├── cases/         # 案件資料夾 (case_YYYYMMDD_NNNN/)
├── users/         # 使用者 JSON
├── sessions/      # LINE 對話狀態
└── locks/         # 檔案鎖

webgis/            # WebGIS 展示頁面 (Leaflet.js)
tests/             # 測試套件
```

## 使用者角色

| 角色 | 說明 |
|------|------|
| 使用者人員 | 現場人員，負責災害通報、照片上傳、案件追蹤 |
| 決策人員 | 管理人員，負責案件審核、資料品質檢視、統計摘要 |

## 六工務段

景美、中和、中壢、新竹、復興、基隆

## API 文件

啟動伺服器後訪問：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 授權

Internal use only — 交通部公路局北區養護工程分局
