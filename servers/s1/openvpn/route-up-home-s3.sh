#!/bin/bash
# Policy routing for the home segment through the S3 exit (tun3).
ip rule add to 10.9.0.0/24 table main pref 110 2>/dev/null || true
ip rule add from 10.9.0.0/24 to 192.168.0.0/24 table main pref 111 2>/dev/null || true
ip rule add from 10.9.0.0/24 table vpn pref 120 2>/dev/null || true
# unbound (10.10.0.1) must resolve through the S3 exit, not through ens3.
ip rule add from 10.10.0.1 table vpn pref 130 2>/dev/null || true
ip route replace default dev tun3 table vpn
