#!/usr/bin/env python3
"""Parse a vless:// subscription link and test it with a real xray client.

Read-only. Verifies that what a subscriber actually receives works.

Usage: link_probe.py 'vless://...' [xray-binary]
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse

XRAY = sys.argv[2] if len(sys.argv) > 2 else "/usr/local/x-ui/bin/xray-linux-amd64"
SOCKS = int(os.environ.get("XRAY_SOCKS_PORT", "10970"))


def parse(url):
    u = urllib.parse.urlparse(url)
    q = dict(urllib.parse.parse_qsl(u.query))
    return {
        "addr": u.hostname,
        "port": u.port,
        "id": u.username,
        "sec": q.get("security", "reality"),
        "sni": q.get("sni"),
        "pbk": q.get("pbk"),
        "pcs": q.get("pcs"),
        "sid": q.get("sid"),
        "spx": q.get("spx", "/"),
        "fp": q.get("fp"),
        "alpn": q.get("alpn"),
        "flow": q.get("flow", ""),
    }


def build(p):
    user = {"id": p["id"], "encryption": "none", "flow": p["flow"]}
    if p["sec"] == "reality":
        stream = {"network": "tcp", "security": "reality",
                  "realitySettings": {"serverName": p["sni"], "fingerprint": p["fp"] or "firefox",
                                      "publicKey": p["pbk"], "shortId": p["sid"],
                                      "spiderX": p["spx"]}}
    else:
        tls = {"allowInsecure": False, "serverName": p["sni"] or p["addr"]}
        if p["fp"]:
            tls["fingerprint"] = p["fp"]
        if p["pcs"]:
            tls["pinnedPeerCertSha256"] = p["pcs"]
        if p["alpn"]:
            tls["alpn"] = p["alpn"].split(",")
        stream = {"network": "tcp", "security": "tls", "tlsSettings": tls}
    return {"log": {"loglevel": "warning"},
            "inbounds": [{"tag": "i", "listen": "127.0.0.1", "port": SOCKS, "protocol": "socks",
                          "settings": {"auth": "noauth", "udp": False}}],
            "outbounds": [{"tag": "o", "protocol": "vless",
                           "settings": {"vnext": [{"address": p["addr"], "port": p["port"],
                                                   "users": [user]}]},
                           "streamSettings": stream}]}


p = parse(sys.argv[1])
print("link: %s:%s sec=%s sni=%s fp=%s alpn=%s" % (p["addr"], p["port"], p["sec"], p["sni"], p["fp"], p["alpn"]))

f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
json.dump(build(p), f)
f.close()
proc = subprocess.Popen([XRAY, "run", "-c", f.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(3)
    ok = 0
    for i in range(3):
        r = subprocess.run(["curl", "-s", "--max-time", "10", "--socks5-hostname",
                            "127.0.0.1:%d" % SOCKS, "https://ifconfig.me"], capture_output=True, text=True)
        out = r.stdout.strip()
        print("  attempt %d -> %s" % (i + 1, out or "<TIMEOUT>"))
        ok += 1 if out else 0
    print("RESULT: %d/3" % ok)
    sys.exit(0 if ok == 3 else 1)
finally:
    proc.send_signal(signal.SIGTERM)
    time.sleep(1)
    os.unlink(f.name)
