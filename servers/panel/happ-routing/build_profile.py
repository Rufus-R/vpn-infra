#!/usr/bin/env python3
"""Сборка ссылки happ://routing/onadd/... из direct-domains.txt.

Профиль: GlobalProxy=true, домены из списка идут напрямую (мимо VPN),
остальное через VPN. Скрипт ничего не пишет на диск и не ходит в сеть:
печатает ссылку (или JSON с --json) в stdout. Секретов в профиле нет.
Куда вставлять ссылку и как проверять — docs/checkpoint-2026-10-21-routing.md.
"""
import argparse
import base64
import json
import re
import sys
import time
from pathlib import Path

NAME = "Shtil-direct"
GEOIP_URL = "https://cdn.jsdelivr.net/gh/hydraponique/roscomvpn-geoip@202602190502/release/geoip.dat"
GEOSITE_URL = "https://cdn.jsdelivr.net/gh/hydraponique/roscomvpn-geosite@202602181705/release/geosite.dat"
DOMAINS_FILE = Path(__file__).with_name("direct-domains.txt")
PLAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
PREFIXED = re.compile(r"^(domain|full|keyword|geosite):\S+$")


def load(path):
    rules, seen = [], set()
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        if PREFIXED.match(line):
            rule = line
        elif PLAIN.match(line):
            rule = "domain:" + line
        else:
            sys.exit(f"{path.name}:{n}: недопустимая запись: {raw.strip()!r}")
        if rule not in seen:
            seen.add(rule)
            rules.append(rule)
    if not rules:
        sys.exit("список пуст: профиль без правил не собираем")
    return rules


def profile(rules):
    return {
        "Name": NAME,
        "GlobalProxy": "true",
        "RemoteDns": "",
        "DomesticDns": "",
        "Geoipurl": GEOIP_URL,
        "Geositeurl": GEOSITE_URL,
        "LastUpdated": str(int(time.time())),
        "DnsHosts": {},
        "DirectSites": rules,
        "DirectIp": [],
        "ProxySites": [],
        "ProxyIp": [],
        "BlockSites": [],
        "BlockIp": [],
        "DomainStrategy": "AsIs",
    }


def main():
    ap = argparse.ArgumentParser(description="Ссылка профиля Happ из списка доменов")
    ap.add_argument("--json", action="store_true", help="печатать JSON профиля вместо ссылки")
    ap.add_argument("--file", type=Path, default=DOMAINS_FILE, help="файл со списком доменов")
    args = ap.parse_args()
    text = json.dumps(profile(load(args.file)), ensure_ascii=False, indent=2)
    if args.json:
        print(text)
    else:
        print("happ://routing/onadd/" + base64.b64encode(text.encode("utf-8")).decode("ascii"))


if __name__ == "__main__":
    main()
