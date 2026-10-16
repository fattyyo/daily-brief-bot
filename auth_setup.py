"""一次性執行：完成 Google OAuth 授權，儲存 token.json"""
import sys
sys.path.insert(0, ".")
from google_services import _get_credentials

print("正在啟動 Google OAuth 授權流程...")
print("瀏覽器會自動開啟，請登入並授權。")
try:
    creds = _get_credentials()
    print("✅ 授權成功！token.json 已儲存。")
    print("現在可以執行 python bot.py 啟動 Bot 了。")
except Exception as e:
    print(f"❌ 授權失敗：{e}")
