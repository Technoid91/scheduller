import requests
import os

MONTHS_UA = [
    "", "січень", "лютий", "березень", "квітень", "травень", "червень",
    "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"
]

def send_to_telegram(pdf_path: str, token: str, chat_ids_str: str, year: int, month: int) -> dict:
    """Send PDF to one or multiple Telegram chats (chat_ids_str comma-separated)."""
    chat_ids = [cid.strip() for cid in chat_ids_str.split(",") if cid.strip()]
    if not chat_ids:
        return {"status": "error", "message": "Не указан ни один chat_id"}

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    caption = f"📋 Графік чергувань — {MONTHS_UA[month]} {year}"

    results = []
    for chat_id in chat_ids:
        try:
            with open(pdf_path, "rb") as f:
                resp = requests.post(url, data={
                    "chat_id": chat_id,
                    "caption": caption
                }, files={"document": (os.path.basename(pdf_path), f, "application/pdf")})
            if resp.status_code == 200 and resp.json().get("ok"):
                results.append(f"✓ {chat_id}")
            else:
                err = resp.json().get("description", "неизвестная ошибка")
                results.append(f"✗ {chat_id}: {err}")
        except Exception as e:
            results.append(f"✗ {chat_id}: {e}")

    all_ok = all(r.startswith("✓") for r in results)
    return {
        "status": "ok" if all_ok else "error",
        "message": "Отправлено: " + ", ".join(results)
    }
