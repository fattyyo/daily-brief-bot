import asyncio
import logging
import time
from datetime import datetime, timedelta

import discord
import config
import scheduler
import google_services
import claude_nlp
import message_builder
import matcha_monitor
from google_services import GoogleAuthExpiredError

MATCHA_TRIGGER_WORDS = {"抹茶庫存", "查抹茶", "抹茶補貨", "matcha", "matcha stock"}
AUTH_EXPIRED_REPLY = "⚠️ Google 授權已過期，需要手動重新登入才能修復（跑一次 `python3 auth_setup.py`），麻煩找人處理一下。"

# 刪除行程需要使用者確認：channel_id -> {"candidates": [...], "expires_at": epoch}
_pending_deletions: dict[int, dict] = {}
PENDING_DELETE_TTL_SECONDS = 60

# 抹茶庫存監控連續失敗計數，達門檻才主動告警，避免每次瞬斷都吵你
_matcha_fail_count = 0
MATCHA_FAIL_ALERT_THRESHOLD = 3      # 連續失敗 3 次（約 30 分鐘）先提醒一次
MATCHA_FAIL_REMINDER_INTERVAL = 18   # 之後每再失敗 18 次（約 3 小時）才提醒一次，避免洗版

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


async def send_morning_brief():
    channel = client.get_channel(config.DISCORD_CHANNEL_ID)
    if not channel:
        log.error("找不到 Discord 頻道 ID: %s", config.DISCORD_CHANNEL_ID)
        return
    try:
        today = datetime.now(config.LOCAL_TZ)
        today_str = today.strftime("%Y-%m-%d")
        is_monday = today.weekday() == 0

        if is_monday:
            week_end = (today + timedelta(days=6)).strftime("%Y-%m-%d")
            events = google_services.get_events_by_range(today_str, week_end)
        else:
            events = google_services.get_today_events()

        tasks = google_services.get_today_tasks()
        emails = google_services.get_important_emails()
        text = message_builder.build_morning_brief(events, tasks, emails, is_weekly=is_monday)
        await channel.send(text)
        log.info("早晨摘要已發送")
    except GoogleAuthExpiredError:
        log.error("發送早晨摘要失敗：Google 授權過期")
        await channel.send(AUTH_EXPIRED_REPLY)
    except Exception as e:
        log.error("發送早晨摘要失敗: %s", e)
        await channel.send("⚠️ 早晨摘要取得失敗，請稍後再試。")


async def send_matcha_alert():
    global _matcha_fail_count
    channel = client.get_channel(config.DISCORD_CHANNEL_ID)
    if not channel:
        log.error("找不到 Discord 頻道 ID: %s", config.DISCORD_CHANNEL_ID)
        return
    try:
        result = await matcha_monitor.check()
        _matcha_fail_count = 0
        restocked = result["restocked"]
        if restocked:
            await channel.send(message_builder.build_matcha_alert(restocked))
            log.info("抹茶補貨通知已發送：%s", [p["name"] for p in restocked])
        elif result["quiet_hours"] is not None:
            await channel.send(
                message_builder.build_matcha_idle_report(result["products"], result["quiet_hours"])
            )
            log.info("抹茶無補貨回報已發送（已 %.1f 小時沒補貨）", result["quiet_hours"])
    except Exception as e:
        _matcha_fail_count += 1
        log.error("檢查抹茶庫存失敗（連續第 %d 次）: %s", _matcha_fail_count, e)
        should_alert = _matcha_fail_count == MATCHA_FAIL_ALERT_THRESHOLD or (
            _matcha_fail_count > MATCHA_FAIL_ALERT_THRESHOLD
            and (_matcha_fail_count - MATCHA_FAIL_ALERT_THRESHOLD) % MATCHA_FAIL_REMINDER_INTERVAL == 0
        )
        if should_alert:
            await channel.send(
                f"⚠️ 抹茶庫存監控已經連續失敗 {_matcha_fail_count} 次，"
                f"可能是網站改版或被 Cloudflare 擋掉了，麻煩找人檢查一下（詳細錯誤看 bot.log）。"
            )


@client.event
async def on_ready():
    log.info("Bot 已上線：%s", client.user)
    scheduler.start(send_morning_brief, send_matcha_alert)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    if message.channel.id != config.DISCORD_CHANNEL_ID:
        return

    text = message.content.strip()
    if not text:
        return

    pending = _pending_deletions.get(message.channel.id)
    if pending:
        if time.time() > pending["expires_at"]:
            del _pending_deletions[message.channel.id]
            # 過期就當作一般訊息繼續往下處理，不特別提示，直接讓使用者重新講一次意圖
        elif text.isdigit():
            del _pending_deletions[message.channel.id]
            choice = int(text)
            candidates = pending["candidates"]
            if choice == 0 or choice > len(candidates):
                await message.reply("已取消刪除。")
            else:
                target = candidates[choice - 1]
                try:
                    google_services.delete_event_by_id(target["id"])
                    await message.reply(
                        f"🗑️ 已刪除行事曆：**{target['title']}**"
                        f"（{message_builder.format_event_time(target['start'])}）"
                    )
                except GoogleAuthExpiredError:
                    log.error("刪除行事曆失敗：Google 授權過期")
                    await message.reply(AUTH_EXPIRED_REPLY)
                except Exception as e:
                    log.error("刪除行事曆失敗: %s", e)
                    await message.reply("⚠️ 刪除行事曆失敗，請稍後再試。")
            return
        else:
            await message.reply("請回覆數字確認要刪除哪一筆（回覆 0 取消）。")
            return

    if text.lower() in MATCHA_TRIGGER_WORDS:
        async with message.channel.typing():
            try:
                products = await matcha_monitor.fetch_products()
                await message.reply(message_builder.build_matcha_status(products))
            except Exception as e:
                log.error("查詢抹茶庫存失敗: %s", e)
                await message.reply("⚠️ 查詢抹茶庫存失敗，請稍後再試。")
        return

    async with message.channel.typing():
        try:
            result = claude_nlp.parse_intent(text)
        except Exception as e:
            log.error("Claude NLP 解析失敗: %s", e)
            await message.reply("⚠️ 解析失敗，請稍後再試。")
            return

    intent = result.get("intent", "other")
    title = result.get("title", "")
    dt_str = result.get("datetime")
    description = result.get("description", "")

    if intent == "add_calendar":
        try:
            dt = datetime.fromisoformat(dt_str) if dt_str else None
            if not dt:
                await message.reply("請告訴我要加到行事曆的具體時間！")
                return
            google_services.add_calendar_event(title, dt, description)
            await message.reply(f"✅ 已加入行事曆：**{title}**（{dt.strftime('%m/%d %H:%M')}）")
        except GoogleAuthExpiredError:
            log.error("新增行事曆失敗：Google 授權過期")
            await message.reply(AUTH_EXPIRED_REPLY)
        except Exception as e:
            log.error("新增行事曆失敗: %s", e)
            await message.reply("⚠️ 新增行事曆失敗，請稍後再試。")

    elif intent == "add_task":
        try:
            google_services.add_task(title, description)
            await message.reply(f"✅ 已加入待辦：**{title}**")
        except GoogleAuthExpiredError:
            log.error("新增 Task 失敗：Google 授權過期")
            await message.reply(AUTH_EXPIRED_REPLY)
        except Exception as e:
            log.error("新增 Task 失敗: %s", e)
            await message.reply("⚠️ 新增待辦失敗，請稍後再試。")

    elif intent == "delete_calendar":
        try:
            candidates = google_services.find_matching_events(title)
            if not candidates:
                await message.reply(f"找不到「{title}」相關的行程，請確認名稱是否正確。")
            else:
                _pending_deletions[message.channel.id] = {
                    "candidates": candidates,
                    "expires_at": time.time() + PENDING_DELETE_TTL_SECONDS,
                }
                await message.reply(message_builder.build_delete_candidates(candidates))
        except GoogleAuthExpiredError:
            log.error("搜尋行事曆失敗：Google 授權過期")
            await message.reply(AUTH_EXPIRED_REPLY)
        except Exception as e:
            log.error("搜尋行事曆失敗: %s", e)
            await message.reply("⚠️ 刪除行事曆失敗，請稍後再試。")

    elif intent == "query":
        try:
            query_start = result.get("query_start")
            query_end = result.get("query_end")
            today = datetime.now(config.LOCAL_TZ).strftime("%Y-%m-%d")
            start = query_start or today
            end = query_end or today
            events = google_services.get_events_by_range(start, end)
            tasks = google_services.get_today_tasks()
            label = f"{start}" if start == end else f"{start} ~ {end}"
            reply = message_builder.build_query_reply(events, tasks, label)
            await message.reply(reply)
        except GoogleAuthExpiredError:
            log.error("查詢行程失敗：Google 授權過期")
            await message.reply(AUTH_EXPIRED_REPLY)
        except Exception as e:
            log.error("查詢行程失敗: %s", e)
            await message.reply("⚠️ 查詢失敗，請稍後再試。")

    else:
        await message.reply("我不太確定你的意思，可以再說清楚嗎？\n例如：「明天下午三點開會」或「待辦：準備報告」")


if __name__ == "__main__":
    client.run(config.DISCORD_BOT_TOKEN)
