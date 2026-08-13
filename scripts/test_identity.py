import json
import urllib.request


def post(path, data):
    req = urllib.request.Request(
        "http://127.0.0.1:8000" + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


r = post(
    "/chat",
    {
        "message": "i am going out tonight tease him about being a cuck",
        "role": "domme",
        "room": "private",
    },
)
print(r["reply"])
print("---")
posts = r.get("group_posts") or []
joined = "\n".join(posts).lower()
print("OK_IN_CHARGE", "in charge" in joined)
print("MENTIONS_MISTRESS_OUT", "mistress" in joined and "going out" in joined)
print("BAD_WHILE_I_ENJOY", "while i enjoy" in joined)
