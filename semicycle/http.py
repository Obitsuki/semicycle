"""HTTP 호출: 재시도·지수 백오프, 오류 메시지에서 API 키 제거."""
import time
import urllib.error
import urllib.parse
import urllib.request

_SECRETS = []


def register_secrets(values):
    for v in values:
        if v and len(v) >= 8:
            _SECRETS.extend({v, urllib.parse.quote(v, safe=""), urllib.parse.quote_plus(v)})


def redact(text):
    s = str(text)
    for v in _SECRETS:
        s = s.replace(v, "***")
    return s


class FetchError(RuntimeError):
    pass


def get(url, headers=None, timeout=60, retries=6, backoff=2.0):
    req = urllib.request.Request(url, headers={"User-Agent": "semicycle", **(headers or {})})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            body = e.read()[:300]
            last = f"HTTP {e.code}: {body!r}"
            if e.code in (400, 401, 403, 404):
                break  # 재시도해도 같은 결과
        except Exception as e:  # 연결 끊김·타임아웃 등
            last = repr(e)
        time.sleep(min(backoff * (i + 1), 20))
    raise FetchError(redact(f"{url} -> {last}"))
