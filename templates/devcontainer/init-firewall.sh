#!/usr/bin/env bash
# aidd dev container: deny outbound traffic by default, and allow HTTPS and SSH only to the hosts in
# /etc/aidd-egress/allowed-hosts, which the image build wrote from devcontainer.json's build args.
#
# Runs as root through sudo on every container start (postStartCommand). It takes no arguments and reads no
# environment, so an agent that runs it again gets the same list. It needs the NET_ADMIN and NET_RAW capabilities.
# Only once its own check passes does it write /run/aidd-egress/active, root-owned, which `aidd doctor --autopilot`
# reads as "the firewall is up". It removes that file first, so a start that fails leaves none, and its first line
# names this start (the boot and PID 1's start time), so a marker from an earlier start counts as stale.
#
# Limits, on purpose simple: host names resolve to IPv4 addresses once, at start; a host whose addresses change
# (a CDN) may need a restart. IPv6 is denied outright. DNS goes only to the resolvers in /etc/resolv.conf, which can
# still carry data out by name lookups: this reduces what a compromised agent can reach, it does not make it safe.
set -euo pipefail

ALLOW=/etc/aidd-egress/allowed-hosts
SET=aidd-egress
ACTIVE_DIR=/run/aidd-egress
ACTIVE="$ACTIVE_DIR/active"

[ "$(id -u)" -eq 0 ] || { echo "aidd-init-firewall: run as root (sudo)" >&2; exit 1; }
rm -f "$ACTIVE"
[ -r "$ALLOW" ] || { echo "aidd-init-firewall: $ALLOW is missing" >&2; exit 1; }

mapfile -t hosts < <(grep -Ev '^[[:space:]]*(#|$)' "$ALLOW")
code_host=$(head -n 1 /etc/aidd-egress/code-host)

# Resolve everything first, while outbound traffic is still open.
addresses=()
for host in "${hosts[@]}"; do
  [[ "$host" =~ ^[A-Za-z0-9.-]+$ ]] || { echo "aidd-init-firewall: not a host name: $host" >&2; exit 1; }
  mapfile -t found < <(getent ahostsv4 "$host" | awk '{print $1}' | sort -u)
  [ "${#found[@]}" -gt 0 ] || { echo "aidd-init-firewall: $host does not resolve" >&2; exit 1; }
  addresses+=("${found[@]}")
done
# GitHub serves git and its API from published ranges, not only from the addresses github.com resolves to.
if [ "$code_host" = github.com ]; then
  mapfile -t ranges < <(curl -fsS --max-time 20 https://api.github.com/meta | jq -r '(.web + .api + .git)[] | select(test(":") | not)')
  [ "${#ranges[@]}" -gt 0 ] || { echo "aidd-init-firewall: could not read GitHub's address ranges" >&2; exit 1; }
  addresses+=("${ranges[@]}")
fi

# The filter table only: Docker's embedded DNS lives in the nat table, which stays as it is.
iptables -F
iptables -X
ipset destroy "$SET" 2>/dev/null || true
ipset create "$SET" hash:net
for a in "${addresses[@]}"; do
  [[ "$a" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}(/[0-9]{1,2})?$ ]] || { echo "aidd-init-firewall: not an IPv4 address: $a" >&2; exit 1; }
  ipset add "$SET" "$a" -exist
done

iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
while read -r ns; do
  [[ "$ns" =~ ^[0-9.]+$ ]] || continue
  iptables -A OUTPUT -d "$ns" -p udp --dport 53 -j ACCEPT
  iptables -A OUTPUT -d "$ns" -p tcp --dport 53 -j ACCEPT
done < <(awk '/^nameserver/ {print $2}' /etc/resolv.conf)
iptables -A OUTPUT -p tcp --dport 443 -m set --match-set "$SET" dst -j ACCEPT
iptables -A OUTPUT -p tcp --dport 22 -m set --match-set "$SET" dst -j ACCEPT
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP
# Refuse the rest at once, so a blocked tool fails fast instead of timing out.
iptables -A OUTPUT -j REJECT --reject-with icmp-admin-prohibited

# IPv6 is denied outright. With IPv6 on, that takes ip6tables, and any failure of it stops the start (set -e) rather
# than leave IPv6 open; with IPv6 off (or not built into the kernel) there is no IPv6 traffic to deny.
IPV6_SWITCH=/proc/sys/net/ipv6/conf/all/disable_ipv6
if [ -r "$IPV6_SWITCH" ] && [ "$(cat "$IPV6_SWITCH")" != 1 ]; then
  command -v ip6tables >/dev/null 2>&1 || { echo "aidd-init-firewall: IPv6 is enabled and ip6tables is missing, so IPv6 cannot be denied" >&2; exit 1; }
  ip6tables -F
  ip6tables -X
  ip6tables -A INPUT -i lo -j ACCEPT
  ip6tables -A OUTPUT -o lo -j ACCEPT
  ip6tables -P INPUT DROP
  ip6tables -P FORWARD DROP
  ip6tables -P OUTPUT DROP
fi

# Check both ways: an allowed host answers, and a host off the list does not.
if curl -fsS --max-time 5 -o /dev/null https://example.com; then
  echo "aidd-init-firewall: example.com is reachable; the firewall is not working" >&2
  exit 1
fi
curl -sS --max-time 10 -o /dev/null "https://$code_host" || { echo "aidd-init-firewall: $code_host is not reachable" >&2; exit 1; }
mkdir -p "$ACTIVE_DIR"
if [ -L "$ACTIVE_DIR" ] || [ ! -d "$ACTIVE_DIR" ] || [ ! -O "$ACTIVE_DIR" ]; then
  echo "aidd-init-firewall: $ACTIVE_DIR is not root's own folder" >&2
  exit 1
fi
chmod 0755 "$ACTIVE_DIR"
start_line="aidd-start unknown"
if read -r boot < /proc/sys/kernel/random/boot_id && read -r pid1 < /proc/1/stat; then
  read -r -a fields <<< "${pid1##*) }"
  start_line="aidd-start $boot ${fields[19]}"
fi
{ printf '%s\n' "$start_line"; printf '%s\n' "${hosts[@]}"; } > "$ACTIVE"
chmod 0644 "$ACTIVE"
echo "aidd-init-firewall: outbound traffic allowed only to: ${hosts[*]}"
