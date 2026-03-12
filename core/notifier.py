import urllib.request
import urllib.parse


def send_bark(url: str, title: str, body: str):
    """通过 Bark 发送推送通知（url 为空时静默跳过）"""
    if not url:
        return
    try:
        encoded = urllib.parse.quote(body, safe="")
        full_url = f"{url.rstrip('/')}/{urllib.parse.quote(title)}/{encoded}"
        urllib.request.urlopen(full_url, timeout=5)
    except Exception:
        pass
