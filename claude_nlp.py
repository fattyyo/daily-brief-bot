import json
import logging
from datetime import datetime
from groq import Groq
import config

log = logging.getLogger(__name__)
_client = Groq(api_key=config.GROQ_API_KEY)

_SYSTEM_PROMPT = """你是一個幫助使用者管理行程的助理。
使用者會用自然語言告訴你他想做什麼。
請分析使用者的意圖，並用以下 JSON 格式回覆（只能回傳 JSON，不要有任何其他文字）：

{
  "intent": "add_calendar" | "add_task" | "query" | "delete_calendar" | "other",
  "title": "事項標題",
  "datetime": "ISO 8601 格式的時間，例如 2026-06-07T15:00:00，若無時間則為 null",
  "query_start": "查詢起始日期 YYYY-MM-DD，僅 intent=query 時填寫，否則為 null",
  "query_end": "查詢結束日期 YYYY-MM-DD，僅 intent=query 時填寫，否則為 null",
  "description": "補充說明（可為空字串）"
}

規則：
- 使用者提到具體時間（幾點、幾月幾日等）→ intent 為 add_calendar，datetime 填入對應時間
- 使用者說的是純待辦、沒有具體時間 → intent 為 add_task，datetime 為 null
- 使用者說「刪掉」、「取消」、「移除」某個行程 → intent 為 delete_calendar，title 填入要刪除的事項名稱
- 使用者詢問行程或待辦 → intent 為 query，並填入 query_start / query_end：
  - 「今天」→ 今天到今天
  - 「明天」→ 明天到明天
  - 「這週」→ 本週一到本週日
  - 「下週」→ 下週一到下週日
  - 「本月」→ 本月第一天到最後一天
  - 若沒有特定範圍 → 今天到今天
- 完全無法判斷 → intent 為 other
- 今天的日期是 {today}，請以此推算所有相對日期
"""


def parse_intent(text: str) -> dict:
    today = datetime.now(config.LOCAL_TZ).strftime("%Y-%m-%d")
    system = _SYSTEM_PROMPT.replace("{today}", today)

    response = _client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        max_tokens=256,
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Groq 回傳的內容無法解析成 JSON，原始內容：%r", raw)
        return {"intent": "other", "title": "", "datetime": None, "description": ""}
