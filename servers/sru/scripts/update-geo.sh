#!/bin/bash
# Update Xray geo-assets for Marzban
cd /opt/marzban/xray-assets || exit 1
wget -qO geoip.dat https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat
wget -qO geosite.dat https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat
cd /opt/marzban && docker compose restart marzban
