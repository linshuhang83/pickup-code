import logging
import urllib.parse
import urllib.request

log = logging.getLogger("notifier")

BARK_API = "https://api.day.app/{key}/{title}/{body}"


def send_bark(bark_key: str, title: str, body: str) -> bool:
    """Bark 推送；失败返回 False，不抛异常。"""
    if not bark_key:
        return False
    url = BARK_API.format(
        key=urllib.parse.quote(bark_key, safe=""),
        title=urllib.parse.quote(title, safe=""),
        body=urllib.parse.quote(body, safe=""),
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            ok = resp.status == 200
    except Exception as e:
        log.warning("Bark 推送失败: %s", e)
        return False
    if not ok:
        log.warning("Bark 推送失败: HTTP %s", resp.status)
        return False
    return True


def notify_new_package(bark_key: str, station: str, pickup_code: str, express: str | None) -> bool:
    title = f"新取件码 {pickup_code}"
    body = f"{station}"
    if express:
        body += f" · {express}"
    body += "，请及时取件"
    return send_bark(bark_key, title, body)
