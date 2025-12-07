# Server Security Configuration

This document outlines security hardening steps for the DigitalOcean droplet hosting this backend.

## ⚠️ Important

**Execute these steps carefully to avoid locking yourself out of the server.**

Always keep an active SSH session open while making security changes, and test new connections in a separate terminal before closing existing ones.

---

## 1. SSH Hardening

### Prerequisites
- Ensure you have SSH key authentication set up
- Test SSH key login works before proceeding
- Keep an active SSH session open during these changes

### Steps

#### 1.1 Verify SSH Key Authentication Works

```bash
# From your local machine
ssh root@your-droplet-ip

# If this works, proceed. If not, set up SSH keys first.
```

#### 1.2 Backup SSH Configuration

```bash
# On the server
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
```

#### 1.3 Edit SSH Configuration

```bash
# On the server
sudo nano /etc/ssh/sshd_config
```

Find and modify these lines (or add them if they don't exist):

```
# Disable password authentication
PasswordAuthentication no

# Disable root login with password (key-only)
PermitRootLogin prohibit-password

# Optional: Disable root login entirely (use sudo user instead)
# PermitRootLogin no

# Ensure public key authentication is enabled
PubkeyAuthentication yes
```

#### 1.4 Test Configuration

```bash
# On the server
# Test the configuration for syntax errors
sudo sshd -t

# If no errors, reload SSH service
sudo systemctl reload sshd
```

#### 1.5 Verify New Connection Works

**IMPORTANT: Keep your current SSH session open!**

```bash
# From your local machine, in a NEW terminal
ssh root@your-droplet-ip

# If this works, you're good. If not, fix the issue using your existing session.
```

---

## 2. DigitalOcean Firewall Configuration

### Overview

Create a firewall that:
- Allows SSH only from your home IP
- Allows HTTP/HTTPS from anywhere
- Denies everything else

### Steps

#### 2.1 Get Your Home IP Address

```bash
# From your local machine
curl ifconfig.me
```

Note this IP address (e.g., `203.0.113.45`).

#### 2.2 Create Firewall in DigitalOcean Dashboard

1. Log in to DigitalOcean
2. Navigate to: **Networking** → **Firewalls**
3. Click **Create Firewall**

#### 2.3 Configure Inbound Rules

| Type | Protocol | Port Range | Sources |
|------|----------|------------|---------|
| SSH | TCP | 22 | Your Home IP (e.g., `203.0.113.45`) |
| HTTP | TCP | 80 | All IPv4, All IPv6 |
| HTTPS | TCP | 443 | All IPv4, All IPv6 |

**Important:** Make sure to specify ONLY your home IP for SSH access.

#### 2.4 Configure Outbound Rules

Keep the default:
- **All TCP, UDP, ICMP** to **All IPv4, All IPv6**

(Your server needs to be able to make outbound connections for package updates, Docker pulls, etc.)

#### 2.5 Apply to Droplet

1. In the **Apply to Droplets** section, select your backend droplet
2. Click **Create Firewall**

#### 2.6 Verify Access

```bash
# From your home IP - should work
ssh root@your-droplet-ip

# From a different network - should be blocked
# (Test using mobile hotspot if available)
```

---

## 3. Additional Security Recommendations

### 3.1 Keep System Updated

```bash
# On the server
sudo apt update && sudo apt upgrade -y
```

Set up automatic security updates:

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 3.2 Enable UFW (Firewall on Server)

**Note:** If using DigitalOcean Firewall, UFW is optional but provides defense in depth.

```bash
# On the server
# Allow SSH first to avoid lockout
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### 3.3 Secure Docker Socket

The Docker socket has root privileges. Ensure it's not exposed:

```bash
# On the server
# Check docker socket permissions
ls -l /var/run/docker.sock

# Should show: srw-rw---- 1 root docker
```

### 3.4 Environment Variables Security

Never commit `.env` files with real credentials to Git:

```bash
# On the server, create .env from template
cp .env.example .env
nano .env

# Update with real credentials
```

Ensure `.env` is in `.gitignore`:

```bash
# Check .gitignore includes
cat .gitignore | grep .env
```

### 3.5 Monitor Failed Login Attempts

```bash
# On the server
# View failed SSH attempts
sudo grep "Failed password" /var/log/auth.log

# Install fail2ban for automatic blocking
sudo apt install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 4. Backup and Recovery

### 4.1 Enable DigitalOcean Backups

1. Go to your Droplet settings
2. Enable **Backups** (costs 20% of droplet price)
3. Backups run weekly automatically

### 4.2 Database Backups

Set up automated PostgreSQL backups:

```bash
# On the server
# Create backup script
cat > /root/backup-db.sh <<'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
docker exec backend-db-1 pg_dump -U backend_user backend_db > /root/backups/db_$DATE.sql
# Keep only last 7 days
find /root/backups -name "db_*.sql" -mtime +7 -delete
EOF

chmod +x /root/backup-db.sh
mkdir -p /root/backups

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /root/backup-db.sh") | crontab -
```

---

## 5. Troubleshooting

### Locked Out of SSH

**Prevention:** Always keep an active session open when making SSH changes.

**If locked out:**
1. Use DigitalOcean Console Access (Droplets → Access → Launch Console)
2. Revert SSH config: `sudo cp /etc/ssh/sshd_config.backup /etc/ssh/sshd_config`
3. Reload SSH: `sudo systemctl reload sshd`

### Firewall Blocking Legitimate Traffic

1. Go to DigitalOcean → Networking → Firewalls
2. Edit the firewall rules
3. Add your current IP to SSH sources

### Cannot Access Services After Firewall Setup

Check that ports 80 and 443 are allowed from all IPs in the firewall rules.

---

## Security Checklist

- [ ] SSH key authentication configured and tested
- [ ] Password authentication disabled in SSH config
- [ ] DigitalOcean firewall created with correct rules
- [ ] Firewall applied to droplet
- [ ] SSH access tested from allowed IP
- [ ] HTTPS access tested from any IP
- [ ] `.env` file created with secure passwords
- [ ] `.env` is in `.gitignore`
- [ ] System packages updated
- [ ] Automatic security updates enabled
- [ ] Database backups configured
- [ ] Droplet backups enabled

---

**Last updated:** 2025-12-07
**For questions or issues, review the DigitalOcean documentation:**
- [SSH Key Setup](https://docs.digitalocean.com/products/droplets/how-to/add-ssh-keys/)
- [Cloud Firewalls](https://docs.digitalocean.com/products/networking/firewalls/)
