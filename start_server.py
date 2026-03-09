"""
一鍵啟動伺服器 — FastAPI + ngrok + 自動設定 LINE Webhook

用法: 雙擊此檔案 或 python start_server.py
按 Ctrl+C 停止所有服務
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys

# Windows cp950 terminal 無法輸出 emoji/特殊 Unicode，強制 UTF-8 避免 crash
if sys.platform == 'win32':
    for _stream_name in ('stdout', 'stderr'):
        _stream = getattr(sys, _stream_name, None)
        if _stream and hasattr(_stream, 'reconfigure'):
            _stream.reconfigure(encoding='utf-8', errors='replace')
import time

from dotenv import load_dotenv

# 切換到專案根目錄
os.chdir(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(".env")
load_dotenv("secrets.private.env", override=True)

PORT = int(os.environ.get("APP_PORT", "8000"))
NGROK_AUTHTOKEN = os.environ.get("NGROK_AUTHTOKEN", "")
NGROK_DOMAIN = os.environ.get("NGROK_DOMAIN", "")


def _set_line_webhook(webhook_url: str) -> bool:
    """Call LINE API to set the webhook endpoint URL automatically."""
    try:
        token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
        if not token:
            print("[WARNING] LINE_CHANNEL_ACCESS_TOKEN 未設定，無法自動更新 webhook。")
            return False

        import urllib.request
        import json

        req = urllib.request.Request(
            "https://api.line.me/v2/bot/channel/webhook/endpoint",
            data=json.dumps({"endpoint": webhook_url}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        if status == 200:
            print(f"[OK] LINE Webhook 已自動更新: {webhook_url}")
            return True
        else:
            print(f"[WARNING] LINE Webhook 更新回傳 HTTP {status}")
            return False
    except Exception as e:
        print(f"[WARNING] 無法自動更新 LINE Webhook: {e}")
        return False



def _kill_port(port: int) -> None:
    """Kill any process currently listening on the given port (Windows)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                if pid > 0:
                    print(f"[INFO] Port {port} 已被 PID {pid} 佔用，正在釋放...")
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        capture_output=True, timeout=5,
                    )
                    time.sleep(1)
                    print(f"[OK] PID {pid} 已終止，Port {port} 已釋放")
                    return
    except Exception as e:
        print(f"[WARNING] 自動釋放 Port {port} 失敗: {e}")



def main():
    print("=" * 50)
    print("  邊坡災害通報與資訊整合管理系統")
    print("  啟動中...")
    print("=" * 50)

    # ── Step 1: 啟動 ngrok (固定域名) ──
    print("\n[1/3] 啟動 ngrok 通道 (固定域名: {})...".format(NGROK_DOMAIN))
    public_url = None
    ngrok_module = None
    try:
        from pyngrok import conf, ngrok
        ngrok_module = ngrok

        if not NGROK_AUTHTOKEN:
            raise ValueError("NGROK_AUTHTOKEN 未設定")
        if not NGROK_DOMAIN:
            raise ValueError("NGROK_DOMAIN 未設定")

        conf.get_default().auth_token = NGROK_AUTHTOKEN
        conf.get_default().region = "ap"
        tunnel = ngrok.connect(
            str(PORT),
            bind_tls=True,
            domain=NGROK_DOMAIN,
        )
        public_url = tunnel.public_url
        # 確保使用 https
        if public_url and public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://", 1)
    except Exception as e:
        print(f"[WARNING] ngrok 啟動失敗: {e}")
        print("  FastAPI 仍會啟動，但外部無法連入。")
        print("  提示: 確認 ngrok 未在其他地方運行 (只能有一個 tunnel)")

    # ── Step 2: 更新 .env + LINE Webhook ──
    webhook_url = None
    if public_url:
        print(f"\n[2/3] 自動更新設定...")
        webhook_url = f"{public_url}/webhook"
        _set_line_webhook(webhook_url)
    else:
        print("\n[2/3] ngrok 未啟動，跳過自動設定。")

    # ── Step 3: 啟動 FastAPI（讀取已更新的 .env） ──
    _kill_port(PORT)
    print("\n[3/3] 啟動 FastAPI 伺服器 (port {})...".format(PORT))
    uvicorn_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", str(PORT)],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    # 等待伺服器啟動
    time.sleep(3)
    if uvicorn_proc.poll() is not None:
        print("[ERROR] FastAPI 啟動失敗！請檢查 .env 和相依套件。")
        sys.exit(1)
    print("[OK] FastAPI 已啟動: http://127.0.0.1:{}".format(PORT))

    # ── 顯示資訊 ──
    print("\n" + "=" * 50)
    print("  [OK] 全部啟動完成！")
    print("=" * 50)
    print(f"  本機:     http://127.0.0.1:{PORT}")
    print(f"  健康檢查: http://127.0.0.1:{PORT}/health")
    print(f"  WebGIS:   http://127.0.0.1:{PORT}/webgis/")
    print(f"  統計:     http://127.0.0.1:{PORT}/webgis/stats.html")
    if public_url:
        print(f"  ngrok:    {public_url}")
        print(f"  Webhook:  {webhook_url}")
        print(f"  Word下載: {public_url}/api/cases/{{case_id}}/word")
    print("=" * 50)
    print("  按 Ctrl+C 停止所有服務")
    print("=" * 50)

    # ── 等待中斷 ──
    def shutdown(sig=None, frame=None):
        print("\n正在關閉服務...")
        uvicorn_proc.terminate()
        try:
            uvicorn_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            uvicorn_proc.kill()
        if public_url and ngrok_module is not None:
            try:
                ngrok_module.kill()
            except Exception:
                pass
        print("[OK] 已關閉。")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        uvicorn_proc.wait()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
