import json
import urllib.request


def post(path, data):
    req = urllib.request.Request(
        "http://127.0.0.1:8000" + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)


try:
    r = post(
        "/api/image",
        {
            "prompt": "moody cinematic portrait of a confident woman in black, soft neon, adult fashion editorial, no nudity",
            "role": "domme",
            "room": "private",
            "post_to_room": False,
        },
    )
    print("OK", r.get("url"), r.get("model"))
except Exception as e:
    print("FAIL", e)
    if hasattr(e, "read"):
        print(e.read().decode())
