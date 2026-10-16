import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# 使用者所在時區（IANA 名稱），影響「今天/明天」判讀、每日摘要發送時間、
# 以及新增到 Google Calendar 事件的時區。用 ZoneInfo 而非固定 UTC 偏移，
# 是因為芝加哥有日光節約時間（CDT/CST 會變動），台北沒有但芝加哥有。
LOCAL_TZ_NAME = os.getenv("LOCAL_TZ", "America/Chicago")
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "8"))
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", "0"))
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
# 每幾分鐘檢查一次抹茶庫存。設 0 ＝暫停自動監控（手動查詢仍可用）。
MATCHA_CHECK_INTERVAL_MINUTES = int(os.getenv("MATCHA_CHECK_INTERVAL_MINUTES", "10"))
# 連續這麼多小時都沒有任何商品補貨，就主動回報一次「目前還是沒貨」，
# 讓你知道監控還活著。設 0 可關閉這個定期回報。
MATCHA_IDLE_REPORT_HOURS = float(os.getenv("MATCHA_IDLE_REPORT_HOURS", "3"))
GOOGLE_TOKEN_PATH = "token.json"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/gmail.readonly",
]
