# Network security (OCI NSG + ufw + fail2ban + Bastion)

> Reference for /webstack:infra slash command and security-auditor SubAgent and tofu-plan-analyzer SubAgent.
> Defense-in-depth for webstack's single OCI VM: VCN + NSG + ufw + fail2ban + optional Bastion.

---

## What is webstack network security

webstack's backend runs on a single Oracle Cloud Infrastructure (OCI) Ampere A1 ARM VM (Ubuntu 22.04). Because this is a public-internet-facing host with no reverse-NAT, no VPN gateway, and no private subnet, every security control must be deliberate and explicit.

**The single-VM baseline (default).** Out of the box, two controls are enough and are what every webstack VM should have: the **OCI NSG** (SSH limited to your admin IP; only 80/443 open for Caddy) and **SSH key policy** (key-only auth, hardened `sshd_config`). Caddy on 443 → `localhost:8080` is the only public path; Spring Boot's 8080 is never exposed. Everything else in this document is an **opt-in defense-in-depth layer** you add as the project's exposure grows — not a prerequisite for a working, reasonably-secured deployment.

**Opt-in layers (add if/when you need them).** ufw (a host-firewall belt to the NSG's braces), fail2ban + the `recidive` jail (SSH brute-force rate-limiting), the OCI Bastion Service (close port 22 entirely), and the Cloudflare CIDR allowlist (only when the API record is proxied) each harden a specific surface:

| Layer | Technology | Status | Scope |
|---|---|---|---|
| Cloud perimeter | OCI VCN + NSG | **baseline** | Packet-level allow/deny before traffic reaches the VM's NIC |
| SSH access policy | key-only `sshd_config` | **baseline** | Authentication hardening for the one open admin port |
| Host firewall | ufw | opt-in | Kernel-level iptables rules echoing the NSG inside the VM |
| Intrusion prevention | fail2ban (+ recidive) | opt-in | Rate-limit brute-force attempts; temporary IP bans |
| SSH without a public port | OCI Bastion | opt-in | Removes port 22 from the internet entirely |
| Origin lockdown | Cloudflare CIDR allowlist | opt-in (proxied mode only) | Restricts 80/443 to Cloudflare edge IPs |

Each layer is independent: a misconfiguration in one does not open a path if the others are correct. The NSG blocks traffic at the Oracle hypervisor; ufw (if enabled) enforces the same rules in the VM kernel; fail2ban (if enabled) watches auth logs and bans repeat offenders.

This document covers the baseline first, then each opt-in layer, the OCI Bastion Service as an alternative to direct SSH, SSH key policy, the optional Cloudflare CIDR allowlist, Spring Boot Actuator isolation, and anti-patterns to avoid.

---

## Why NSG over Security Lists

Oracle offers two VCN firewall mechanisms:

**Security Lists** apply to a subnet. Every VNIC in the subnet inherits the same rules. This is coarse-grained: changing the security posture of one VM requires creating a new subnet or changing rules that affect all VMs in the subnet.

**Network Security Groups (NSGs)** apply to specific VNICs — a per-resource attachment. A single VNIC can belong to up to 5 NSGs, and rules are evaluated with OR logic (traffic is allowed if any NSG covering the VNIC permits it).

Oracle's own documentation recommends NSGs for new architectures because they:

- Decouple security from subnet topology — VMs with different security needs can share a subnet.
- Allow referencing other NSGs as rule source/destination (not just CIDRs) — useful for future multi-VM layouts.
- Support targeted rule updates via `UpdateNetworkSecurityGroupSecurityRules`, avoiding full rule-list re-submission.
- Are stateful by default — established connections do not require explicit return rules.

webstack uses **one NSG per VM**, attached to the VNIC at instance creation. The subnet retains a minimal Security List with only the VCN-local ICMP rules Oracle creates by default; all ingress/egress policy lives in the NSG.

---

## VCN basic configuration

The VCN layout for a webstack single-VM deployment:

| Resource | Value | Notes |
|---|---|---|
| VCN CIDR | `10.0.0.0/16` | Standard private range |
| Internet Gateway | one per VCN | Bidirectional inbound + outbound internet |
| Public subnet | `10.0.0.0/24` | VM lives here; assign public IP at VNIC |
| Route table | `0.0.0.0/0 → IGW` | Default route; attached to public subnet |
| NAT Gateway | not needed | VM has a public IP — NAT is for private subnets |

NAT Gateways are relevant only when VMs lack public IPs and need outbound-only internet access. The webstack VM has an assigned public IP, so the Internet Gateway covers both directions. Do not provision a NAT Gateway unless you add a private subnet.

The VCN, Internet Gateway, route table, and subnet resources are documented in `infrastructure/oracle-cloud-setup.md`. No additional networking infrastructure is needed for the single-VM layout. The relevant security resources live in the NSG section below.

---

## Inbound NSG rule matrix

The NSG defines which traffic the OCI hypervisor admits before it reaches the VM. Start with deny-all (no rules = no traffic) and add only what is necessary.

### Standard rule set

| Priority | Direction | Protocol | Source | Port | Description |
|---|---|---|---|---|---|
| 1 | Ingress | TCP | `0.0.0.0/0` | 80 | HTTP (Caddy ACME + redirect) |
| 2 | Ingress | TCP | `0.0.0.0/0` | 443 | HTTPS (Caddy TLS termination) |
| 3 | Ingress | TCP | `<admin-ip>/32` | 22 | SSH from operator IP only |
| 4 | Ingress | ICMP | `0.0.0.0/0` | type 3, code 4 | Path MTU discovery |
| 5 | Egress | All | `0.0.0.0/0` | All | Unrestricted outbound |

Replace `<admin-ip>/32` with your actual public IP (check `curl -s https://checkip.amazonaws.com`). If using the OCI Bastion Service (see next section), remove rule 3 entirely.

Port 8080 (Spring Boot) must **not** appear in this table. All application traffic enters through Caddy on port 443; Caddy proxies to `localhost:8080` internally. See [Spring Boot Actuator endpoint](#spring-boot-actuator-endpoint).

### OpenTofu NSG resources

```hcl
resource "oci_core_network_security_group" "app" {
  compartment_id = var.oci_compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "webstack-nsg-app"
}

# HTTP + HTTPS open to the world (Caddy terminates TLS; Spring Boot is localhost-only)
resource "oci_core_network_security_group_security_rule" "ingress_web" {
  for_each                  = toset(["80", "443"])
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  tcp_options {
    destination_port_range { min = tonumber(each.value); max = tonumber(each.value) }
  }
}

# SSH restricted to the operator's IP — remove this rule when using Bastion
resource "oci_core_network_security_group_security_rule" "ingress_ssh" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "${var.admin_ip}/32"
  source_type               = "CIDR_BLOCK"
  tcp_options { destination_port_range { min = 22; max = 22 } }
}

resource "oci_core_network_security_group_security_rule" "egress_all" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
}
```

Attach the NSG at instance creation via `create_vnic_details { nsg_ids = [oci_core_network_security_group.app.id] }` (see `oracle-cloud-setup.md` for the full instance resource).

---

## OCI Bastion Service option

### What it is

The OCI Bastion Service provides time-limited, IAM-authenticated SSH access to compute instances without requiring a public SSH port. It resides in the public subnet and creates a short-lived tunneled SSH session through Oracle's managed infrastructure. The connection is audited via OCI Audit service automatically.

Bastions do not incur charges and have service-level session limits (see OCI service limits documentation for current values). For a solo developer, the practical limit is sufficient.

### When to use it

Use Bastion when you want SSH port 22 completely closed — no inbound SSH from any public IP whatsoever. This is the most secure posture and eliminates the entire brute-force surface on port 22 at the NSG level.

| Approach | NSG rule 3 | SSH exposure |
|---|---|---|
| Direct SSH (operator IP) | `<admin-ip>/32 → 22` | SSH port open to one IP |
| Bastion (recommended) | None — remove rule 3 | SSH port 22 closed entirely |

### Setup procedure

1. **Enable the Bastion plugin** on the VM's Oracle Cloud Agent:
   - Console → Compute → Instance → Oracle Cloud Agent tab.
   - Enable the **Bastion** plugin.

1. **Create the Bastion resource** (OpenTofu):

```hcl
resource "oci_bastion_bastion" "main" {
  bastion_type                 = "STANDARD"
  compartment_id               = var.oci_compartment_id
  target_subnet_id             = oci_core_subnet.public.id
  name                         = "webstack-bastion"
  client_cidr_block_allow_list = ["${var.admin_ip}/32"]
}
```

1. **Create a session** when you need access (one-off, not persisted):

```bash
oci bastion session create-managed-ssh \
  --bastion-id <bastion-ocid> \
  --target-resource-id <instance-ocid> \
  --target-os-username ubuntu \
  --ssh-public-key-file ~/.ssh/id_ed25519.pub \
  --session-ttl-in-seconds 3600
```

1. **Connect** using the SSH command OCI prints after session creation:

```bash
# OCI generates this command; copy it from the console or CLI output
ssh -o ProxyCommand='ssh -W %h:%p -p 22 ocid1.bastionsession.<region>.<session-ocid>@host.bastion.<region>.oci.oraclecloud.com' \
    -p 22 ubuntu@<instance-private-ip>
```

The session expires after `--session-ttl-in-seconds`. There is no persistent SSH daemon listening on a public port.

### NSG adjustment for Bastion-only mode

When using Bastion, remove `ingress_ssh` from the NSG. The Bastion service enforces `client_cidr_block_allow_list` on its own side; SSH access arrives from Bastion's internal address over the VCN. To allow Bastion-tunneled connections while blocking direct public SSH, add an ingress rule scoped to the VCN CIDR instead of `0.0.0.0/0`:

```hcl
# Allow SSH only from within the VCN (Bastion-proxied) — no direct public SSH
resource "oci_core_network_security_group_security_rule" "ingress_bastion_ssh" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction   = "INGRESS"
  protocol    = "6"
  source      = "10.0.0.0/16"   # VCN CIDR — Bastion lives here
  source_type = "CIDR_BLOCK"
  tcp_options { destination_port_range { min = 22; max = 22 } }
}
```

---

## Host hardening

The NSG blocks traffic at the Oracle hypervisor. ufw and fail2ban operate inside the VM and provide an **opt-in** second line of defense that is independent of OCI configuration — add them when you want host-level redundancy, not as a prerequisite for the baseline single-VM deployment.

### ufw — host firewall

ufw (Uncomplicated Firewall) wraps iptables/nftables with a simple CLI. It is stateful: established connections are tracked automatically; only inbound policy needs explicit rules.

Install and configure on Ubuntu 22.04:

```bash
sudo apt install -y ufw

# Default policy: deny all inbound, allow all outbound
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow HTTP/HTTPS from anywhere
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow SSH only from the admin IP (same restriction as NSG rule 3)
# Replace <admin-ip> with your public IP
sudo ufw allow from <admin-ip> to any port 22 proto tcp

# Enable (applies rules immediately, persists across reboots)
sudo ufw enable

# Verify
sudo ufw status verbose
```

Verify with `sudo ufw status verbose` — the output should list 80/tcp and 443/tcp as `ALLOW IN Anywhere`, and 22/tcp as `ALLOW IN <admin-ip>` only.

If using Bastion-only mode, omit the `ufw allow 22/tcp` line. ufw's deny-all default already blocks it.

**Rule order matters.** ufw evaluates rules in sequence and stops at the first match. More specific rules (IP-restricted port 22) must come before broader rules (allow all TCP). The order shown above is correct.

### fail2ban — SSH brute-force prevention

fail2ban monitors log files for failed authentication attempts and inserts temporary iptables ban rules. For SSH, it reads `/var/log/auth.log` (Ubuntu) and bans IPs that exceed the threshold.

Install:

```bash
sudo apt install -y fail2ban
```

Create a local override (never edit `/etc/fail2ban/jail.conf` directly — it is overwritten on package upgrades):

```bash
sudo tee /etc/fail2ban/jail.d/sshd.local << 'EOF'
[sshd]
enabled   = true
port      = ssh
filter    = sshd
logpath   = /var/log/auth.log
maxretry  = 5
findtime  = 600
bantime   = 3600
banaction = ufw
EOF
```

Configuration key:

| Parameter | Value | Meaning |
|---|---|---|
| `maxretry` | 5 | Ban after 5 failed attempts |
| `findtime` | 600 | Count failures in the past 10 minutes |
| `bantime` | 3600 | Ban duration: 1 hour |
| `banaction` | ufw | Use ufw to insert the ban rule (integrates with host firewall) |

Restart and verify:

```bash
sudo systemctl enable fail2ban
sudo systemctl restart fail2ban

# Check jail status
sudo fail2ban-client status sshd

# List currently banned IPs
sudo fail2ban-client get sshd banip
```

**Escalating bans.** For persistent offenders, enable fail2ban's built-in `recidive` jail by adding `/etc/fail2ban/jail.d/recidive.local` with `enabled = true`, `bantime = 604800` (7 days), `findtime = 86400`, `maxretry = 3`. It reads fail2ban's own log and re-bans IPs that were already banned multiple times.

---

## SSH key & policy

### sshd_config hardening

Drop a file in `/etc/ssh/sshd_config.d/` so package upgrades do not overwrite it:

```
# /etc/ssh/sshd_config.d/webstack-hardening.conf
PermitRootLogin no
PasswordAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
AllowUsers ubuntu
LogLevel VERBOSE
AllowTcpForwarding no
GatewayPorts no
PermitTunnel no
ClientAliveInterval 300
ClientAliveCountMax 2
```

`ClientAliveCountMax 0` would drop a session after a single missed keepalive (~5 min) — disruptive even for an active operator on a brief pause. `2` (with the 300 s interval) idles out an unresponsive session at ~15 minutes while leaving working sessions intact. Lower it deliberately only if a strict idle-timeout policy requires it.

Test and apply:

```bash
sudo sshd -t && sudo systemctl reload ssh
```

### ed25519 key generation

ed25519 is the preferred algorithm: 256-bit elliptic curve, compact (68-char public key), fast, and resistant to side-channel timing attacks. RSA 4096 is acceptable if interoperability with legacy tools is required but is slower and larger.

Generate a new ed25519 key pair on your local machine (not on the server):

```bash
ssh-keygen -t ed25519 -C "webstack-$(date +%Y%m)" -f ~/.ssh/webstack_ed25519
ssh-copy-id -i ~/.ssh/webstack_ed25519.pub ubuntu@<vm-ip>
```

The `-C` comment embeds the creation month — useful for tracking rotation age.

### Key rotation policy

Rotate keys annually: generate a new ed25519 pair, add the public key to `/home/ubuntu/.ssh/authorized_keys`, verify the new key logs in, then remove the old key. Remove departed team members' keys immediately. On suspected compromise, revoke first and investigate after.

The initial public key is injected at instance creation via `metadata.ssh_authorized_keys` (see `oracle-cloud-setup.md`). Subsequent additions require an active SSH session to edit `authorized_keys` directly.

---

## Cloudflare CIDR allowlist (optional)

If Cloudflare proxying is enabled for the `api.example.com` record (orange cloud mode — see `infrastructure/domain-and-tls.md`), all requests to your VM originate from Cloudflare's edge nodes, not end-user IPs. In this case, you can restrict the NSG ingress rules for ports 80/443 to only Cloudflare's published CIDR ranges, blocking all non-Cloudflare inbound traffic to the application ports.

**Note:** webstack's default uses DNS-only mode (gray cloud) for the API subdomain, which means requests come directly from user IPs. The Cloudflare CIDR allowlist applies only if you switch the `api` record to proxied mode.

### Current Cloudflare CIDR ranges

**Fetch the ranges at apply time — do not rely on the static list below.** Cloudflare publishes the authoritative lists at `https://www.cloudflare.com/ips-v4/` and `https://www.cloudflare.com/ips-v6/`; pull them into `var.cloudflare_ipv4_cidrs`/`var.cloudflare_ipv6_cidrs` (via the refresh cron in [CIDR refresh](#cidr-refresh), or an `http` data source) so the NSG rules are always current. The snapshot below is illustrative only and **will go stale**; it is shown so you know the shape, not to be copied verbatim. As of the last verified date (see footer):

**IPv4:**

```
103.21.244.0/22
103.22.200.0/22
103.31.4.0/22
104.16.0.0/13
104.24.0.0/14
108.162.192.0/18
131.0.72.0/22
141.101.64.0/18
162.158.0.0/15
172.64.0.0/13
173.245.48.0/20
188.114.96.0/20
190.93.240.0/20
197.234.240.0/22
198.41.128.0/17
```

**IPv6:**

```
2400:cb00::/32
2606:4700::/32
2803:f800::/32
2405:b500::/32
2405:8100::/32
2a06:98c0::/29
2c0f:f248::/32
```

### CIDR refresh

Cloudflare's ranges change infrequently but do change. Refresh them with a monthly cron on the VM:

```bash
#!/usr/bin/env bash
# /opt/scripts/refresh-cf-cidrs.sh — run on the first of each month
set -euo pipefail
curl -fsSL https://www.cloudflare.com/ips-v4/ > /opt/scripts/cf-ipv4.txt
curl -fsSL https://www.cloudflare.com/ips-v6/ > /opt/scripts/cf-ipv6.txt
echo "Updated $(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

```
# crontab entry
0 2 1 * * /opt/scripts/refresh-cf-cidrs.sh >> /var/log/cf-cidr-refresh.log 2>&1
```

After a range update, re-run `tofu apply` with the updated `var.cloudflare_ipv4_cidrs` list to update NSG rules. Review the diff before applying — a botched update locks out all web traffic.

### OpenTofu NSG rules for Cloudflare-only mode

Replace the `ingress_web` rule with per-CIDR ingress rules scoped to `var.cloudflare_ipv4_cidrs`:

```hcl
variable "cloudflare_ipv4_cidrs" {
  type    = list(string)
  # Current list: https://www.cloudflare.com/ips-v4/ — refresh before applying
  default = ["103.21.244.0/22", "103.22.200.0/22", "104.16.0.0/13", ...]
}

resource "oci_core_network_security_group_security_rule" "ingress_cf_https" {
  for_each                  = toset(var.cloudflare_ipv4_cidrs)
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  tcp_options { destination_port_range { min = 443; max = 443 } }
}
```

---

## Spring Boot Actuator endpoint

Spring Boot Actuator exposes health, metrics, environment, and heap dump endpoints. By default the management endpoints share the application port (8080). Actuator endpoints must **never** be reachable from the internet.

**webstack keeps management on the application port (8080), not a separate 8081.** The whole Spring Boot app — `/api/**` plus `/actuator/**` — listens only on `localhost:8080`; Caddy on 443 is the sole public entry point and proxies to it. This is the port every other webstack doc assumes for health checks (`http://localhost:8080/actuator/health`, the deploy health gate, the keepalive crons, UptimeRobot's BE monitor). The defenses below keep the actuator surface private without splitting the port:

**1. The app binds to loopback.** Spring listens on `localhost:8080` (`server.address=127.0.0.1`), so 8080 is never directly reachable from outside the VM regardless of firewall state. Port 8080 is **not** in the NSG rule matrix and must never be added; ufw's `deny incoming` default blocks it on the host too.

**2. Do not proxy `/actuator/**` to the public.** Caddy reverse-proxies only the public application paths. Either omit `/actuator/**` from the proxied routes, or restrict it in Caddy/Spring Security so health/metrics/heapdump are not exposed through 443. Verify:

```bash
# From the VM — internal access works
curl -s http://localhost:8080/actuator/health    # OK — loopback only
# From the public side — actuator must not be served through Caddy
curl -s https://api.example.com/actuator/env      # Must 404/403 — never reachable
curl -s http://<vm-public-ip>:8080/actuator       # Must timeout/refuse — 8080 is loopback-only
```

**Prometheus scraping** of Actuator metrics must happen from within the VM (Prometheus running on the same host) or via SSH port forwarding. Never open a public route to the actuator endpoints.

Cross-link: Prometheus configuration and Actuator metric scraping are documented in `docs/backend/observability.md`.

---

## Anti-patterns

**Port 22 open to `0.0.0.0/0`.** SSH-scanning bots connect within minutes of provisioning. Restrict to `<admin-ip>/32` or use the Bastion Service so port 22 is closed entirely.

**Password authentication enabled.** `PasswordAuthentication yes` allows dictionary and credential-stuffing attacks. Disable unconditionally; all access must use public-key authentication.

**Spring Boot Actuator exposed externally.** `server.address` not set defaults to all interfaces; an NSG rule opening port 8080, or proxying `/actuator/**` through Caddy, exposes `/actuator/env`, `/actuator/heapdump`, and `/actuator/shutdown` — leaking secrets and allowing remote shutdown. Bind the app to `127.0.0.1`, keep 8080 out of the NSG, and do not route actuator paths through Caddy.

**Cloudflare proxied + origin NSG allows `0.0.0.0/0`.** When the `api` record is orange-cloud proxied, Cloudflare DDoS protection can be bypassed by hitting the OCI IP directly. Restrict origin ingress to Cloudflare CIDRs when using proxied mode.

**`ALLOW ALL` NSG rule.** A blanket `protocol=all, source=0.0.0.0/0` rule added for "debugging" silently overrides all other rules (OR logic). Audit NSG rules periodically; delete blanket-allow rules immediately.

**No fail2ban or equivalent.** ufw rejects banned-IP packets but does not terminate in-progress brute-force sessions. Without fail2ban, bots fill `auth.log` and consume CPU for the full duration. fail2ban bans them within seconds of the threshold.

**RSA 2048 keys.** Use ed25519 for all new keys. Rotate existing RSA 2048 keys on the next scheduled rotation.

---

## Sources

- **OCI Network Security Groups:** https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm — _authoritative_
- **OCI Bastion Service overview:** https://docs.oracle.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm — _authoritative_
- **Ubuntu UFW community guide:** https://help.ubuntu.com/community/UFW — _community: Ubuntu community documentation_
- **fail2ban GitHub wiki:** https://github.com/fail2ban/fail2ban/wiki — _community: fail2ban project_
- **Cloudflare IP ranges:** https://www.cloudflare.com/ips/ — _authoritative_
- **SSH Academy — sshd_config hardening:** https://www.ssh.com/academy/ssh/sshd_config — _community: SSH.com academy_

Last verified: 2026-06-22 (OCI Always Free / OpenSSH 9.X / ufw 0.36.X / fail2ban 1.X / Caddy 2.X).
