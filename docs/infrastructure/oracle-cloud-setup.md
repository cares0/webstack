# Oracle Cloud Setup

> Reference for the infra skill and tofu-plan-analyzer. Covers Oracle Cloud Infrastructure (OCI) Always Free sign-up, the Ampere A1 ARM compute shape, VCN networking, security lists, boot volumes, cloud-init, and the `oracle/oci` IaC provider.

## Why Oracle Cloud for BE

OCI's **Always Free** tier offers a uniquely generous compute allocation: up to **4 OCPU and 24 GB RAM total** of Arm-based Ampere A1 cores, persistent across the account's lifetime (not a 12-month trial). For a Spring Boot backend in dev/staging — and often in early production — this is enough for the whole stack.

Most other clouds either limit free compute to a small x86 burst instance (AWS t2.micro, GCP e2-micro) or hide free credits behind a 12-month expiration. OCI's Always Free is meaningfully different. The trade-off is operational maturity: tooling, docs, and ecosystem lag behind AWS/GCP. webstack's IaC-first approach (OpenTofu) largely sidesteps the docs gap.

## Always Free limits

OCI's Always Free covers:

- **Compute**: 2 AMD VMs (VM.Standard.E2.1.Micro: 1/8 OCPU, 1 GB RAM each), **plus** 4 Arm Ampere A1 OCPU + 24 GB RAM that may be split across up to 4 VMs. webstack uses the Arm side.
- **Block storage**: 200 GB total across volumes.
- **Object storage**: 20 GB Standard + 10 GB Archive + 10 GB Infrequent Access.
- **Database**: 2 free Autonomous Databases (20 GB each) — Always Free.
- **Networking**: 1 VCN with default subnets, internet/NAT gateways. **10 TB outbound transfer per month** (very generous).
- **Load balancer**: 1 Flexible LB at 10 Mbps.

webstack uses Compute (Ampere A1) for the backend and skips OCI's database in favor of Supabase Postgres (better DX for early-stage products). Object storage is unused in v1.

Limits and inclusions can change; the canonical reference is the Oracle Always Free document linked in **Sources** below. Verify current allowances before provisioning if numbers matter for your decision.

## Resource reclamation prevention (do not skip)

OCI **may reclaim Always Free resources** that have been idle for an extended period. The exact threshold is documented as approximately 7 days of idleness for the underlying VM and several months for inactive accounts; the policy is at https://www.oracle.com/cloud/free/faq/. Reclamation deletes the VM and its boot volume — recovery requires re-running `/webstack:infra` to recreate the resources, then re-running `/webstack:deploy` to re-upload the jar.

For a solo developer who launches webstack and steps away (e.g., between feature pushes for a few weeks), this is the single most likely failure mode for an otherwise-zero-cost stack. Two cheap mitigations:

1. **Periodic OCI Console activity**: log into https://cloud.oracle.com at least monthly. Browsing the Compute or Networking pages counts as activity.
2. **Health-check cron from outside OCI**: a cron job on any other always-on machine (a different cloud, a NAS, a Raspberry Pi) that hits the app's health endpoint:

   ```bash
   # crontab entry — every 30 minutes
   */30 * * * * curl -fsS https://<api-domain>/actuator/health > /dev/null 2>&1
   ```

   The HTTP traffic keeps the VM "active" from OCI's perspective and prevents reclamation.

If you do not need always-on staging, accept reclamation as the cost of $0 and document the redeploy procedure in your runbook. webstack's `/webstack:infra` + `/webstack:deploy` together restore the full backend in a few minutes once tokens are re-exported.

## Sign-up

1. Visit https://cloud.oracle.com/free.
2. Click **Start for free**.
3. Provide email, country, and name.
4. **Credit card required** for identity verification only — Always Free resources are never charged. Set the **Always Free** toggle to ensure billing alerts at $0 thresholds are configured later.
5. Choose a **Home Region** thoughtfully — it cannot be changed. webstack default suggestion: `ap-seoul-1` for Korea-based teams; `us-ashburn-1` for global.
6. Create a tenancy name (used in OCIDs).

Account activation typically completes in minutes. If approval is delayed, OCI emails within 24h.

## Tenancy & user

OCI's IAM hierarchy: **tenancy** → **compartments** → **users / groups / policies**. The tenancy is the root. Compartments organize resources for billing and access; users authenticate; policies grant permissions.

For OpenTofu, **do not use the root user**. Create:

1. A **compartment** for the project (e.g., `webstack-myapp`).
2. A **user** for IaC (e.g., `tofu-iac` or `iac-runner`).
3. A **group** containing that user (e.g., `iac-administrators`).
4. A **policy** granting the group `manage all-resources in compartment webstack-myapp`.

Policies are written in OCI's policy language, not IAM JSON; the language is verbose but documented.

## API key for OpenTofu

OpenTofu authenticates via an **API signing key** — an RSA key pair where the public key is uploaded to OCI and the private key signs API requests. (The same key works for any IaC tool that uses the OCI SDK.)

1. Generate locally:

   ```bash
   mkdir -p ~/.oci
   openssl genrsa -out ~/.oci/oci_api_key.pem 2048
   chmod 600 ~/.oci/oci_api_key.pem
   openssl rsa -pubout -in ~/.oci/oci_api_key.pem -out ~/.oci/oci_api_key_public.pem
   ```

2. In OCI Console: **Identity & Security** → **Users** → select the IAM user → **API Keys** → **Add API Key**.
3. Paste the contents of `oci_api_key_public.pem`.
4. Copy the resulting **fingerprint** (e.g., `aa:bb:cc:...`).
5. Note the **tenancy OCID**, **user OCID**, and **region** from the console.

For OpenTofu, set:

```hcl
provider "oci" {
  tenancy_ocid     = var.oci_tenancy_ocid
  user_ocid        = var.oci_user_ocid
  fingerprint      = var.oci_fingerprint
  private_key_path = var.oci_private_key_path
  region           = var.oci_region
}
```

The user fills these values into `<infra>/.env`; the private key path is local; webstack never reads the .env directly.

## VCN setup

Every OCI compute instance lives in a **Virtual Cloud Network (VCN)**. Minimal layout for webstack:

- **VCN** — `10.0.0.0/16`.
- **Internet Gateway (IGW)** — outbound + inbound internet for public subnets.
- **Public subnet** — `10.0.0.0/24`. Application VM lives here.
- **Route table** — default route `0.0.0.0/0` → IGW, attached to the public subnet.
- **Security List** (or Network Security Group, preferred) — allow inbound:
  - 22 from your admin IP only (SSH).
  - 80 / 443 from anywhere (HTTP/S — Caddy terminates TLS on 443 and reverse-proxies to Spring Boot on `localhost:8080`).
  - Spring Boot's 8080 is **never** internet-exposed: Caddy is the only entry point and proxies to it over the loopback. Do not open 8080 in the security list/NSG. See `docs/infrastructure/network-security.md`.

```hcl
resource "oci_core_vcn" "main" {
  compartment_id = var.oci_compartment_id
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "webstack-vcn"
  dns_label      = "webstack"
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = var.oci_compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "webstack-igw"
}

resource "oci_core_subnet" "public" {
  compartment_id    = var.oci_compartment_id
  vcn_id            = oci_core_vcn.main.id
  cidr_block        = "10.0.0.0/24"
  display_name      = "webstack-public"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.app.id]
  dns_label         = "public"
}
```

For production-grade isolation, add a private subnet for the database (skipped in webstack since Supabase is the DB).

## Compute instance — Ampere A1

Ampere A1 is OCI's Arm shape (Neoverse N1). It is **free up to 4 OCPU + 24 GB RAM in aggregate**. A single VM can use up to all 4 OCPU; webstack's default is **2 OCPU + 12 GB RAM** for the app, leaving headroom.

```hcl
data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.oci_compartment_id
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_core_instance" "app" {
  compartment_id      = var.oci_compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_arm.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key_path)
    user_data           = base64encode(file("${path.module}/cloud-init.yaml"))
  }

  display_name = "webstack-app"
}
```

Use **Ubuntu 22.04 ARM** as the base image; OpenJDK 21, snap, systemd are first-class. Skip "Oracle Linux" unless you have a reason. (verify: 22.04 LTS is a deliberate pin here — decide whether to move to 24.04 LTS for a longer support window before provisioning a new VM.)

## Boot volume

The boot volume is provisioned automatically with the instance. The default size is 50 GB, which is adequate for a Spring Boot app with logs; raise it only if you add Docker images or large local artifacts.

```hcl
resource "oci_core_instance" "app" {
  # ... above ...
  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu_arm.images[0].id
    boot_volume_size_in_gbs = 50
  }
}
```

200 GB is the Always Free total across all block storage. One 50 GB boot volume leaves room for additional volumes (logs, backups) if needed.

## Cloud-init for Java + service

`cloud-init.yaml` runs on first boot. It installs Java, fetches the app jar, and registers a systemd unit:

```yaml
#cloud-config
package_update: true
packages:
  - openjdk-21-jre-headless
  - curl
write_files:
  - path: /etc/systemd/system/webstack-app.service
    content: |
      [Unit]
      Description=Webstack Backend
      After=network.target

      [Service]
      User=ubuntu
      WorkingDirectory=/opt/app/current
      ExecStart=/usr/bin/java -jar /opt/app/current/app.jar
      EnvironmentFile=/opt/app/app.env
      Restart=on-failure
      RestartSec=10

      [Install]
      WantedBy=multi-user.target
runcmd:
  # Rollback-capable release layout: /opt/app/releases/<timestamp>/app.jar + a `current` symlink.
  - mkdir -p /opt/app/releases
  - chown -R ubuntu:ubuntu /opt/app
  # First deploy creates releases/<timestamp>/ and repoints `current` at it.
  # Seed a placeholder target so the symlink exists from first boot; deploy overwrites it.
  - install -d -o ubuntu -g ubuntu /opt/app/releases/bootstrap
  - ln -sfn /opt/app/releases/bootstrap /opt/app/current
  - systemctl daemon-reload
  - systemctl enable webstack-app.service
  # webstack-app.service is started after the first deploy uploads the jar and repoints `current`
```

The systemd unit reads `/opt/app/app.env` for `DATABASE_URL`, `SUPABASE_*`, etc. and runs the jar via the `current` symlink (`/opt/app/current/app.jar`). webstack `/webstack:deploy` SCPs the jar into a new `/opt/app/releases/<timestamp>/` directory, repoints `current`, and then `systemctl restart webstack-app` (see `docs/infrastructure/release-management.md` and `backup-and-recovery.md` for the full deploy/rollback sequence).

## oracle/oci provider

The official `oracle/oci` provider covers the entire OCI surface. The HCL is identical for OpenTofu and Terraform; the `terraform { ... }` block name is preserved by OpenTofu for portability. Common resources used by webstack:

- `oci_core_vcn`, `oci_core_subnet`, `oci_core_internet_gateway`, `oci_core_route_table`.
- `oci_core_security_list` or `oci_core_network_security_group` (NSG preferred — simpler rule attachment).
- `oci_core_instance`, `oci_core_volume`, `oci_core_volume_attachment`.
- `oci_objectstorage_bucket` (if using Object Storage).
- `oci_identity_compartment`, `oci_identity_user`, `oci_identity_policy` (for IAM, usually one-time).

Provider config:

```hcl
terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 6.0"
    }
  }
}
```

## webstack convention

- **Provider config:** `infrastructure/main.tf` declares `oracle/oci` pinned to a major version. Auth via `var.oci_tenancy_ocid`, `var.oci_user_ocid`, `var.oci_fingerprint`, `var.oci_private_key_path`, `var.oci_region` — all in `variables.tf`. `var.oci_compartment_id` (typically equal to `var.oci_tenancy_ocid` for solo projects, scoping resources to the root compartment) and `var.oci_ssh_public_key_path` complete the OCI variable set.
- **Compute resources:** `infrastructure/oracle.tf` provisions VCN, public subnet, security list/NSG, and one Ampere A1 instance running Ubuntu 22.04 ARM with cloud-init.
- **Cloud-init:** `infrastructure/cloud-init.yaml` (referenced via `file()`) installs OpenJDK 21, the `webstack-app.service` unit, and provisions the `/opt/app/releases/` directory plus the `current` symlink. The jar is deployed separately via SCP.
- **Public IP** assigned at the VNIC level; the OpenTofu output exposes it for `/webstack:deploy` and DNS configuration.
- **Deployment loop:** `/webstack:deploy` SCPs `build/libs/app.jar` into a fresh `/opt/app/releases/<timestamp>/` directory and an updated `app.env` to `/opt/app/`, repoints the `current` symlink, then `ssh ... systemctl restart webstack-app`. No CI/CD pipeline in v1.
- **Free-tier monitoring:** the infra skill checks `oci_core_instance` count and shape configurations against the 4 OCPU / 24 GB Always Free total before `tofu apply`.

## Sources

- OCI Always Free reference: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- oracle/oci provider (OpenTofu Registry): https://search.opentofu.org/provider/oracle/oci/latest
- Ampere A1 on OCI: https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm
- OCI VCN concepts: https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm
- API signing keys: https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm

Last verified: 2026-06-22 (Always Free Ampere A1 / boot volume 50 GB default / cloud-init releases+current layout).
