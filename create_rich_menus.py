"""
建立 LINE Rich Menu — 決策人員 + 使用者人員
透過 LINE Messaging API 建立、上傳圖片、設定預設、綁定個別使用者。

用法: python create_rich_menus.py
"""
from __future__ import annotations

import json
import os
import sys
from io import BytesIO

import httpx
from PIL import Image, ImageDraw, ImageFont

# ── Config ──────────────────────────────────────────────
ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
if not ACCESS_TOKEN:
    from dotenv import load_dotenv
    load_dotenv()
    ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

MANAGER_USER_ID = os.getenv("BOOTSTRAP_ADMIN_LINE_ID", "U64fa245a3b8e9b38ca0b716a889d71ae")

API = "https://api.line.me/v2/bot"
HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

# Rich Menu: 2500x1686, 2 rows x 3 cols
WIDTH = 2500
HEIGHT = 1686
COLS = 3
ROWS = 2
CELL_W = WIDTH // COLS
CELL_H = HEIGHT // ROWS


# ── Rich Menu definitions ──────────────────────────────

MANAGER_MENU = {
    "size": {"width": WIDTH, "height": HEIGHT},
    "selected": True,
    "name": "決策人員選單",
    "chatBarText": "開啟選單",
    "areas": [
        {"bounds": {"x": 0,           "y": 0,      "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "通報災害"}},
        {"bounds": {"x": CELL_W,      "y": 0,      "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "查詢案件"}},
        {"bounds": {"x": CELL_W * 2,  "y": 0,      "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "審核待辦"}},
        {"bounds": {"x": 0,           "y": CELL_H, "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "查看地圖"}},
        {"bounds": {"x": CELL_W,      "y": CELL_H, "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "統計摘要"}},
        {"bounds": {"x": CELL_W * 2,  "y": CELL_H, "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "個人資訊"}},
    ],
}

USER_MENU = {
    "size": {"width": WIDTH, "height": HEIGHT},
    "selected": True,
    "name": "使用者人員選單",
    "chatBarText": "開啟選單",
    "areas": [
        {"bounds": {"x": 0,           "y": 0,      "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "通報災害"}},
        {"bounds": {"x": CELL_W,      "y": 0,      "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "查詢案件"}},
        {"bounds": {"x": CELL_W * 2,  "y": 0,      "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "操作說明"}},
        {"bounds": {"x": 0,           "y": CELL_H, "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "查看地圖"}},
        {"bounds": {"x": CELL_W,      "y": CELL_H, "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "統計摘要"}},
        {"bounds": {"x": CELL_W * 2,  "y": CELL_H, "width": CELL_W, "height": CELL_H},
         "action": {"type": "message", "text": "個人資訊"}},
    ],
}


# ── Image generation ───────────────────────────────────

# Color palette
COLORS = {
    "通報災害": ("#D32F2F", "🚨"),   # Red
    "查詢案件": ("#1976D2", "🔍"),   # Blue
    "審核待辦": ("#F57C00", "📋"),   # Orange
    "查看地圖": ("#388E3C", "🗺️"),  # Green
    "統計摘要": ("#7B1FA2", "📊"),   # Purple
    "個人資訊": ("#455A64", "👤"),   # Grey
    "操作說明": ("#0097A7", "❓"),   # Teal
}


def _try_font(size: int):
    """Try to load a CJK font."""
    candidates = [
        "C:/Windows/Fonts/msjh.ttc",      # 微軟正黑體
        "C:/Windows/Fonts/msjhbd.ttc",     # 微軟正黑體 Bold
        "C:/Windows/Fonts/msyh.ttc",       # 微軟雅黑
        "C:/Windows/Fonts/simsun.ttc",     # 宋體
        "C:/Windows/Fonts/arial.ttf",      # fallback
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_menu_image(labels: list[str]) -> bytes:
    """Generate a 2500x1686 Rich Menu image with 6 cells."""
    img = Image.new("RGB", (WIDTH, HEIGHT), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    font_label = _try_font(72)
    font_emoji = _try_font(120)

    for idx, label in enumerate(labels):
        col = idx % COLS
        row = idx // COLS
        x0 = col * CELL_W
        y0 = row * CELL_H
        x1 = x0 + CELL_W
        y1 = y0 + CELL_H

        bg_color, emoji = COLORS.get(label, ("#607D8B", "⚙️"))

        # Fill cell background
        draw.rectangle([x0, y0, x1, y1], fill=bg_color)

        # Draw border
        draw.rectangle([x0, y0, x1, y1], outline="#FFFFFF", width=4)

        # Draw label text (centered)
        cx = x0 + CELL_W // 2
        cy = y0 + CELL_H // 2

        # Draw text
        bbox = draw.textbbox((0, 0), label, font=font_label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2 + 20), label, fill="#FFFFFF", font=font_label)

        # Draw a simple icon shape above text
        icon_cy = cy - 80
        draw.ellipse([cx - 50, icon_cy - 50, cx + 50, icon_cy + 50], fill="#FFFFFF40", outline="#FFFFFF", width=3)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── API calls ──────────────────────────────────────────

def delete_all_rich_menus(client: httpx.Client):
    """Delete all existing rich menus to start clean."""
    resp = client.get(f"{API}/richmenu/list", headers=HEADERS)
    if resp.status_code == 200:
        menus = resp.json().get("richmenus", [])
        for menu in menus:
            rid = menu["richMenuId"]
            client.delete(f"{API}/richmenu/{rid}", headers=HEADERS)
            print(f"  Deleted old menu: {rid}")


def create_rich_menu(client: httpx.Client, menu_def: dict) -> str:
    """Create a rich menu and return its ID."""
    resp = client.post(f"{API}/richmenu", headers=HEADERS, json=menu_def)
    resp.raise_for_status()
    rich_menu_id = resp.json()["richMenuId"]
    return rich_menu_id


MAX_IMAGE_SIZE = 1_000_000  # LINE limit: 1 MB


def _compress_image(image_path: str) -> tuple[bytes, str]:
    """Load image, resize to 2500x1686 if needed, compress to JPEG ≤ 1 MB.
    Returns (image_bytes, content_type)."""
    img = Image.open(image_path).convert("RGB")
    # Ensure exact size required by LINE
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
        print(f"  Resized to {WIDTH}x{HEIGHT}")

    # Try JPEG with decreasing quality until ≤ 1 MB
    for quality in (90, 85, 80, 70, 60, 50):
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_IMAGE_SIZE:
            print(f"  Compressed to JPEG quality={quality}, size={len(data):,} bytes")
            return data, "image/jpeg"

    # Fallback: return lowest quality attempt
    print(f"  WARNING: 壓縮後仍為 {len(data):,} bytes，超過 1MB 限制")
    return data, "image/jpeg"


def upload_rich_menu_image(client: httpx.Client, rich_menu_id: str, image_data: bytes, content_type: str = "image/jpeg"):
    """Upload an image for a rich menu."""
    resp = client.post(
        f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
        headers={
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": content_type,
        },
        content=image_data,
        timeout=30.0,
    )
    resp.raise_for_status()


def set_default_rich_menu(client: httpx.Client, rich_menu_id: str):
    """Set a rich menu as the default for all users."""
    resp = client.post(
        f"{API}/user/all/richmenu/{rich_menu_id}",
        headers=HEADERS,
    )
    resp.raise_for_status()


def link_rich_menu_to_user(client: httpx.Client, user_id: str, rich_menu_id: str):
    """Link a specific rich menu to a specific user."""
    resp = client.post(
        f"{API}/user/{user_id}/richmenu/{rich_menu_id}",
        headers=HEADERS,
    )
    resp.raise_for_status()


# ── Main ───────────────────────────────────────────────

def main():
    if not ACCESS_TOKEN:
        print("ERROR: LINE_CHANNEL_ACCESS_TOKEN not set")
        sys.exit(1)

    print("=== 建立 LINE Rich Menu ===\n")

    with httpx.Client(timeout=30.0) as client:
        # Step 1: Clean up old menus
        print("[1/6] 清除舊的 Rich Menu...")
        delete_all_rich_menus(client)

        # Step 2: Create manager menu
        print("[2/6] 建立決策人員 Rich Menu...")
        manager_menu_id = create_rich_menu(client, MANAGER_MENU)
        print(f"  Manager Menu ID: {manager_menu_id}")

        # Step 3: Create user menu
        print("[3/6] 建立使用者人員 Rich Menu...")
        user_menu_id = create_rich_menu(client, USER_MENU)
        print(f"  User Menu ID: {user_menu_id}")

        # Step 4: Load and upload images from files
        print("[4/6] 載入並上傳 Rich Menu 圖片...")
        script_dir = os.path.dirname(os.path.abspath(__file__))

        manager_img_path = os.path.join(script_dir, "rich_menu_manager.png")
        if not os.path.exists(manager_img_path):
            print(f"  ERROR: 找不到決策人員圖片: {manager_img_path}")
            sys.exit(1)
        manager_img, manager_ct = _compress_image(manager_img_path)
        upload_rich_menu_image(client, manager_menu_id, manager_img, manager_ct)
        print(f"  Manager image uploaded ({len(manager_img):,} bytes)")

        user_img_path = os.path.join(script_dir, "rich_menu_user.png")
        if not os.path.exists(user_img_path):
            print(f"  ERROR: 找不到使用者圖片: {user_img_path}")
            sys.exit(1)
        user_img, user_ct = _compress_image(user_img_path)
        upload_rich_menu_image(client, user_menu_id, user_img, user_ct)
        print(f"  User image uploaded ({len(user_img):,} bytes)")

        # Step 5: Set user menu as default (for all new users)
        print("[5/6] 設定使用者人員選單為預設...")
        set_default_rich_menu(client, user_menu_id)
        print(f"  Default menu set to: {user_menu_id}")

        # Step 6: Link manager menu to admin user
        print(f"[6/6] 綁定決策人員選單到管理員 ({MANAGER_USER_ID})...")
        link_rich_menu_to_user(client, MANAGER_USER_ID, manager_menu_id)
        print(f"  Linked {manager_menu_id} to {MANAGER_USER_ID}")

        # Save IDs for future reference
        menu_ids = {
            "manager_rich_menu_id": manager_menu_id,
            "user_rich_menu_id": user_menu_id,
        }
        ids_path = os.path.join(os.path.dirname(__file__), "rich_menu_ids.json")
        with open(ids_path, "w", encoding="utf-8") as f:
            json.dump(menu_ids, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] 完成! Rich Menu IDs 已儲存至 {ids_path}")
    print(f"   決策人員: {manager_menu_id}")
    print(f"   使用者人員: {user_menu_id}")
    print("\n請重新開啟 LINE 聊天室確認選單是否出現。")


if __name__ == "__main__":
    main()
