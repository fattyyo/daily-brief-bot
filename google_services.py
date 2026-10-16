import os
from datetime import datetime, timedelta
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import config

LOCAL_TZ = config.LOCAL_TZ


class GoogleAuthExpiredError(Exception):
    """token.json 的 refresh_token 過期/被撤銷，需要手動重新跑 auth_setup.py 登入，無法自動修復。"""


def _get_credentials():
    creds = None
    if os.path.exists(config.GOOGLE_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(config.GOOGLE_TOKEN_PATH, config.GOOGLE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                raise GoogleAuthExpiredError(
                    "Google 授權已過期，需要手動重新跑 python3 auth_setup.py 登入"
                ) from e
        else:
            flow = InstalledAppFlow.from_client_secrets_file(config.GOOGLE_CREDENTIALS_PATH, config.GOOGLE_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(config.GOOGLE_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def get_events_by_range(start_date: str, end_date: str) -> list[dict]:
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    start_dt = datetime.fromisoformat(start_date).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=LOCAL_TZ
    )
    end_dt = datetime.fromisoformat(end_date).replace(
        hour=23, minute=59, second=59, microsecond=0, tzinfo=LOCAL_TZ
    )

    result = service.events().list(
        calendarId="primary",
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = []
    for item in result.get("items", []):
        start = item["start"].get("dateTime", item["start"].get("date", ""))
        events.append({"title": item.get("summary", "（無標題）"), "start": start})
    return events


def get_today_events() -> list[dict]:
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    return get_events_by_range(today, today)


def get_today_tasks() -> list[dict]:
    creds = _get_credentials()
    service = build("tasks", "v1", credentials=creds)

    lists_result = service.tasklists().list().execute()
    task_list_id = lists_result["items"][0]["id"] if lists_result.get("items") else "@default"

    result = service.tasks().list(
        tasklist=task_list_id,
        showCompleted=False,
        showHidden=False,
    ).execute()

    tasks = []
    for item in result.get("items", []):
        tasks.append({"title": item.get("title", "（無標題）")})
    return tasks


def get_important_emails() -> list[dict]:
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    now = datetime.now(LOCAL_TZ)
    after_epoch = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    query = f"is:unread in:inbox after:{after_epoch}"

    result = service.users().messages().list(userId="me", q=query, maxResults=10).execute()
    messages = []
    for msg in result.get("messages", []):
        detail = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
                                                metadataHeaders=["Subject", "From"]).execute()
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        messages.append({
            "subject": headers.get("Subject", "（無主旨）"),
            "sender": headers.get("From", "未知寄件者"),
        })
    return messages


def add_calendar_event(title: str, dt: datetime, description: str = "") -> dict:
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)

    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": dt.isoformat(), "timeZone": config.LOCAL_TZ_NAME},
        "end": {"dateTime": (dt + timedelta(hours=1)).isoformat(), "timeZone": config.LOCAL_TZ_NAME},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return created


def find_matching_events(keyword: str, max_results: int = 5) -> list[dict]:
    """搜尋標題含 keyword 的近期事件（前 7 天到後 60 天），回傳候選清單供使用者確認，不會直接刪除。"""
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(LOCAL_TZ)
    time_min = (now - timedelta(days=7)).isoformat()
    time_max = (now + timedelta(days=60)).isoformat()

    result = service.events().list(
        calendarId="primary",
        q=keyword,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=max_results,
    ).execute()

    return [
        {
            "id": item["id"],
            "title": item.get("summary", keyword),
            "start": item["start"].get("dateTime", item["start"].get("date", "")),
        }
        for item in result.get("items", [])
    ]


def delete_event_by_id(event_id: str):
    creds = _get_credentials()
    service = build("calendar", "v3", credentials=creds)
    service.events().delete(calendarId="primary", eventId=event_id).execute()


def add_task(title: str, description: str = "") -> dict:
    creds = _get_credentials()
    service = build("tasks", "v1", credentials=creds)

    lists_result = service.tasklists().list().execute()
    task_list_id = lists_result["items"][0]["id"] if lists_result.get("items") else "@default"

    task = {"title": title, "notes": description}
    created = service.tasks().insert(tasklist=task_list_id, body=task).execute()
    return created
