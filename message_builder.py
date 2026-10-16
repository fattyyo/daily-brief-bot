from datetime import datetime
import config

LOCAL_TZ = config.LOCAL_TZ

_WEEKDAY_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def _format_time(iso_str: str, show_date: bool = False) -> str:
    try:
        dt = datetime.fromisoformat(iso_str).astimezone(LOCAL_TZ)
        if show_date:
            weekday = _WEEKDAY_ZH[dt.weekday()]
            return dt.strftime(f"%m/%d（{weekday}）%H:%M")
        return dt.strftime("%H:%M")
    except Exception:
        return iso_str


def format_event_time(iso_str: str) -> str:
    """公開版的時間格式化，供刪除確認清單這類跨模組使用（永遠帶日期）。"""
    return _format_time(iso_str, show_date=True)


def build_delete_candidates(candidates: list[dict]) -> str:
    lines = ["🔍 **找到以下符合的行程，請回覆數字確認要刪除哪一筆（回覆 0 取消，60 秒內有效）：**\n"]
    for i, ev in enumerate(candidates, 1):
        lines.append(f"{i}. {ev['title']}｜{format_event_time(ev['start'])}")
    return "\n".join(lines)


def build_morning_brief(events: list[dict], tasks: list[dict], emails: list[dict], is_weekly: bool = False) -> str:
    if is_weekly:
        lines = ["🌅 **早安，Eric！以下是本週的行程摘要：**\n"]
    else:
        lines = ["🌅 **早安，Eric！以下是今天的摘要：**\n"]

    lines.append(f"📅 **行事曆（{len(events)} 件）**")
    if events:
        for e in events:
            lines.append(f"• {_format_time(e['start'], show_date=is_weekly)} — {e['title']}")
    else:
        lines.append("• 今天沒有行事曆事件" if not is_weekly else "• 本週沒有行事曆事件")

    lines.append("")
    lines.append(f"✅ **待辦清單（{len(tasks)} 件）**")
    if tasks:
        for t in tasks:
            lines.append(f"• {t['title']}")
    else:
        lines.append("• 目前沒有待辦事項")

    lines.append("")
    lines.append(f"📬 **未讀重要信件（{len(emails)} 封）**")
    if emails:
        for m in emails:
            lines.append(f"• {m['subject']}　from {m['sender']}")
    else:
        lines.append("• 沒有新的未讀信件")

    return "\n".join(lines)


def build_query_reply(events: list[dict], tasks: list[dict], label: str = "今天") -> str:
    is_range = "~" in label
    lines = [f"📋 **以下是 {label} 的行程與待辦：**\n"]

    lines.append(f"📅 **行事曆（{len(events)} 件）**")
    if events:
        for e in events:
            lines.append(f"• {_format_time(e['start'], show_date=is_range)} — {e['title']}")
    else:
        lines.append("• 這段期間沒有行事曆事件")

    lines.append("")
    lines.append(f"✅ **待辦清單（{len(tasks)} 件）**")
    if tasks:
        for t in tasks:
            lines.append(f"• {t['title']}")
    else:
        lines.append("• 目前沒有待辦事項")

    return "\n".join(lines)


def build_matcha_alert(products: list[dict]) -> str:
    lines = ["🍵 **抹茶補貨通知！以下商品剛恢復現貨：**\n"]
    for p in products:
        lines.append(f"• **{p['name']}**\n  {p['url']}")
    return "\n".join(lines)


def build_matcha_idle_report(products: list[dict], quiet_hours: float) -> str:
    """連續一段時間都沒補貨時的定期回報，順便讓你知道監控還活著。"""
    instock = [p for p in products if p["status"] == "instock"]
    now = datetime.now(LOCAL_TZ).strftime("%m/%d %H:%M")
    hours = round(quiet_hours) if quiet_hours >= 1 else round(quiet_hours, 1)
    if instock:
        names = "、".join(p["name"] for p in instock)
        detail = f"目前現貨（維持中，非新補貨）：{names}"
    else:
        detail = f"{len(products)} 項商品目前全部缺貨。"
    return f"🍵 過去 {hours} 小時沒有任何補貨。{detail}\n（監控正常運作中，最後檢查 {now}）"


def build_matcha_status(products: list[dict]) -> str:
    lines = ["🍵 **抹茶粉庫存狀態：**\n"]
    for p in products:
        icon = "✅ 現貨" if p["status"] == "instock" else "❌ 缺貨"
        lines.append(f"• {p['name']}：{icon}")
    return "\n".join(lines)
