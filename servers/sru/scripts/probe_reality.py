#!/usr/bin/env python3
"""Entry/exit probe for 3x-ui nodes, meant to run from the master (MSK).

Read-only: reads inbound params through the master API and opens test
outbound connections. Nothing is written on S_RU / S3 / master.

Two stages, because they fail differently:

  1. TCP connect    -> network-level block
  2. TLS ClientHello -> payload-level failure (Reality not answering,
                        downstream target dead) while TCP still says OPEN

Stage 2 uses `openssl s_client`, enough to expose the 31.10.2026 incident
(server ACKs the ClientHello and answers nothing). `--xray` adds a full
client check through an xray instance for TLS-type inbounds (S3).

Exit codes: 0 ok, 1 payload hang, 2 TCP unreachable.

Usage:
  probe_reality.py            # S_RU reality entry, TLS stage
  probe_reality.py s3 --xray  # S3 exit, end-to-end through xray
"""
import argparse
import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request

API = "https://127.0.0.1:25305/mzoU2Iuh3snGizVvxa2zBi/panel/api"
TOKEN = "/root/.secrets/panel-bot-token.txt"
XRAY = "/usr/local/x-ui/bin/xray-linux-amd64"

NODES = {
    "sru": {"inbound": 1, "host": "31.77.169.67", "port": 443, "expect_exit": "31.77.169.67"},
    "s3": {"inbound": 8, "host": "195.242.118.2", "port": 10001, "expect_exit": "195.242.118.2"},
}


def api(path):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + open(TOKEN).read().strip()})
    return json.loads(urllib.request.urlopen(req, context=ssl._create_unverified_context()).read())


def inbound(iid):
    obj = api("/inbounds/get/%d" % iid)["obj"]
    settings = obj["settings"]
    settings = json.loads(settings) if isinstance(settings, str) else settings
    stream = obj["streamSettings"]
    stream = json.loads(stream) if isinstance(stream, str) else stream
    client = next((c for c in settings.get("clients", []) if c.get("enable")), None)
    return obj, stream, client


def tcp_open(host, port, timeout=6):
    try:
        return subprocess.run(["bash", "-c", "cat < /dev/null > /dev/tcp/%s/%d" % (host, port)],
                              timeout=timeout).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def tls_hello(host, port, sni, timeout=8):
    try:
        r = subprocess.run(["openssl", "s_client", "-connect", "%s:%d" % (host, port),
                            "-servername", sni], input="", capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return "CONNECTED" in (r.stdout + r.stderr)


def public_key(stream):
    rs = stream.get("realitySettings") or {}
    priv = rs.get("privateKey")
    if not priv:
        return None
    out = subprocess.run([XRAY, "x25519", "-i", priv], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("Password") or "PublicKey" in line:
            return line.rsplit(None, 1)[-1].strip("()")
    return None


def build(host, port, stream, client, socks_port):
    if stream.get("security") == "tls":
        tls = stream.get("tlsSettings") or {}
        inner = tls.get("settings") or {}
        pin = inner.get("pinnedPeerCertSha256")
        pin = pin[0] if isinstance(pin, list) else pin  # server side: list, client side: plain hex
        stream_cfg = {"network": "tcp", "security": "tls",
                      "tlsSettings": {"serverName": inner.get("serverName") or host,
                                      "pinnedPeerCertSha256": pin, "allowInsecure": False,
                                      "alpn": tls.get("alpn") or ["h2", "http/1.1"]}}
    else:
        rs = stream.get("realitySettings") or {}
        stream_cfg = {"network": "tcp", "security": "reality",
                      "realitySettings": {"serverName": rs["serverNames"][0],
                                          "fingerprint": "firefox",
                                          "publicKey": public_key(stream),
                                          "shortId": rs["shortIds"][0],
                                          "spiderX": "/"}}
    return {"log": {"loglevel": "warning"},
            "inbounds": [{"tag": "i", "listen": "127.0.0.1", "port": socks_port, "protocol": "socks",
                          "settings": {"auth": "noauth", "udp": False}}],
            "outbounds": [{"tag": "o", "protocol": "vless",
                           "settings": {"vnext": [{"address": host, "port": port,
                                                   "users": [{"id": client["id"], "encryption": "none",
                                                              "flow": client.get("flow") or ""}]}]},
                           "streamSettings": stream_cfg}]}


def xray_probe(cfg, socks_port, timeout=12):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(cfg, fh)
        path = fh.name
    proc = subprocess.Popen([XRAY, "run", "-c", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(3)
        r = subprocess.run(["curl", "-s", "--max-time", str(timeout), "--socks5-hostname",
                            "127.0.0.1:%d" % socks_port, "https://ifconfig.me"],
                           capture_output=True, text=True)
        return r.stdout.strip()
    finally:
        proc.terminate()
        time.sleep(1)
        os.unlink(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("node", choices=sorted(NODES), nargs="?", default="sru")
    ap.add_argument("--xray", action="store_true", help="full xray client check instead of openssl")
    args = ap.parse_args()
    node = NODES[args.node]

    obj, stream, client = inbound(node["inbound"])
    host, port = node["host"], node["port"]
    label = "%s:%d" % (host, port)

    if not tcp_open(host, port):
        print("%s TCP FAIL" % label)
        return 2

    if args.xray:
        if client is None:
            print("%s: no enabled client in inbound %d" % (label, node["inbound"]))
            return 1
        out = xray_probe(build(host, port, stream, client, 10960), 10960)
        if not out:
            print("%s TCP OK, xray payload TIMEOUT" % label)
            return 1
        print("%s exit=%s (expect %s)" % (label, out, node["expect_exit"]))
        return 0 if out == node["expect_exit"] else 1

    rs = stream.get("realitySettings") or {}
    sni = (rs.get("serverNames") or ["localhost"])[0]
    if not tls_hello(host, port, sni):
        print("%s TCP OK, TLS ClientHello TIMEOUT (sni=%s)" % (label, sni))
        return 1
    print("%s TCP OK, TLS handshake OK (sni=%s)" % (label, sni))
    return 0


if __name__ == "__main__":
    sys.exit(main())
