import os, json, time, urllib.request, urllib.parse, ssl

def load_env(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_env()

def get(url, headers=None, timeout=30, retries=3, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "semicycle-research (contact: owner)", **(headers or {})})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
                return b if raw else b.decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(min(2 * (i + 1), 15))
    raise last

def redact(s):
    for k, v in ENV.items():
        s = s.replace(v, f"<{k}>")
        s = s.replace(urllib.parse.quote(v, safe=""), f"<{k}>")
    return s
