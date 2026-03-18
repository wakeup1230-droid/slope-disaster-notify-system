# 專案通用開發邏輯規格

本文件用於所有專案，確保「開發流程、分支協作、上線節奏」一致。

## 1. 目標

- 任何專案都使用同一套 Git 與 GitHub 流程
- 支援多人平行開發
- 降低衝突與回歸風險
- 保持可追溯、可回滾、可審查

## 2. 分支模型

- `main`: 正式上線版，永遠保持可部署
- `dev`: 整合測試版，功能先在此整合
- `test`: 功能串接與發布前驗證分支
- `feature/<topic>`: 功能分支，個別需求開發
- `hotfix/<topic>`: 緊急修補分支（正式環境重大問題）

## 3. 標準開發流程

1. 從 `dev` 建立功能分支
2. 開發並提交清楚 commit
3. 推送 `feature/*` 並開 PR 到 `dev`
4. 通過 CI + Code Review 後合併到 `dev`
5. `dev` 整合後提升到 `test` 進行串接驗證
6. `test` 驗證完成後，開 PR 到 `main`
7. 合併到 `main` 後觸發 release/deploy

## 3.1 版本規格（每個分支都有版本號）

- 採 Semantic Versioning：`MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`
- `feature/*`: `X.Y.Z-alpha.N`（例：`2.4.0-alpha.3`）
- `dev`: `X.Y.Z-beta.N`（例：`2.4.0-beta.2`）
- `test`: `X.Y.Z-rc.N`（例：`2.4.0-rc.1`）
- `main`: `X.Y.Z`（例：`2.4.0`）
- `hotfix/*`: `X.Y.(Z+1)`（例：`2.4.1`）

## 4. 任務拆分規則（給多人協作）

- 一個需求一個 `feature/*` 分支
- 每個分支盡量聚焦單一主題
- 大需求拆成多個子任務分支，避免長分支
- 功能分支建議壽命 1~3 天，避免漂移

## 5. PR 與審查規格

- PR 必填：變更摘要、影響範圍、驗證方式、風險與回滾
- 至少 1 位 reviewer 核准
- 所有 required checks 必須通過
- 不可帶 unresolved conversation 合併

## 6. Commit 規格

- 使用 `feat/fix/refactor/docs/test/chore` 前綴
- 單一 commit 聚焦單一目的
- 禁止 `update`、`修正` 這類不可追蹤訊息

## 7. 測試與品質門檻

- PR 至少通過：lint、unit tests、build
- 影響核心流程時需補整合測試或 smoke test
- 發版前依 `RELEASE_CHECKLIST.md` 逐項確認

## 8. 上線與回滾

- 上線來源只允許 `main`
- 每次 release 需有可追蹤版本資訊
- 發生重大異常時以回滾方案優先止血

## 9. 安全規範

- 禁止提交 `.env`、金鑰、憑證、token
- 機敏資訊只放 GitHub Secrets
- workflow 權限採最小必要原則

## 10. 專案初始化最低檔案清單

- `.github/workflows/ci.yml`
- `.github/workflows/release-main.yml`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `BRANCHING.md`
- `COMMIT_CONVENTION.md`
- `RELEASE_CHECKLIST.md`
- `DEVELOPMENT_LOGIC.md`
- `VERSIONING_POLICY.md`

## 11. 團隊執行準則

- 不可直接在 `main` 改 code
- 合併/推送前先 pull 同步
- 變更必須經 PR 流程
- 所有專案都套用本規格，不做專案特例
