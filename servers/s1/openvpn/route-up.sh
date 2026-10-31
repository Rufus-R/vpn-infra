#!/bin/bash
# Policy routing rules for 10.9.0.0/24. The vpn table default is set by route-up-home-s3.sh.
ip rule add to 10.9.0.0/24 table main pref 110 2>/dev/null || true
ip rule add from 10.9.0.0/24 to 192.168.0.0/24 table main pref 111 2>/dev/null || true
ip rule add from 10.9.0.0/24 table vpn pref 120 2>/dev/null || true
