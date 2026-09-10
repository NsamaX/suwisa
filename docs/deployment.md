# Debian / Dockge deployment

Run these commands on the server. Use the existing Docker Compose plugin and Dockge stack directory; access SSH/Dockge over Tailscale. No router forwarding or reverse proxy is required.

## First deployment

```bash
cd /opt/stacks
git clone https://github.com/NsamaX/suwisa.git
cd suwisa
cp .env.example .env
chmod 600 .env
mkdir -p data backups
sudo chown 1000:1000 data backups
# Edit .env locally, then:
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 suwisa
```

Required: Discord token, guild ID, allowed user IDs and receipt channel IDs. Docker includes Tesseract and both languages. Compose overrides Windows OCR paths and sets the container database path.

Dockge discovers `/opt/stacks/suwisa/compose.yaml`; rescan its stacks directory if necessary. Keep edits through Dockge synchronized with the Git checkout.

The database is on local storage at `/opt/stacks/suwisa/data/`, outside the container. The read-only container writes only to `/app/data`, `/app/backups`, and temporary `/tmp`. Limits of 768 MB RAM / 1.5 CPU are an initial budget, not measured production requirements; monitor after deployment.

## Acceptance checks

1. Check running/healthy status after connecting to Discord.
2. Invoke `/receipt` with a non-sensitive image in an allowed channel; edit and confirm.
3. Resubmit and confirm the same image; it should report an existing record.
4. Unapproved users/channels must not trigger OCR.
5. Restart and confirm the database survives.
6. Test unattended reboot and lid-closed operation. Configure logind as well as the desktop power manager if the laptop must remain awake without a desktop session. Preserve critical-battery shutdown.

Commands sync to the configured guild during startup. Enable Message Content Intent; presence/member intents are not requested.

## Updates

```bash
cd /opt/stacks/suwisa
docker image tag suwisa:0.1.0 suwisa:previous
docker compose exec -T suwisa suwisa-backup /app/backups/pre-update.sqlite3
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Record the previous commit. Update image tags when publishing a new release. `restart` alone does not apply rebuilt code/config; use `up -d --build`. For rollback, stop the stack and restore prior code/image and a compatible database backup. Do not delete volumes or data to troubleshoot.

## Backup

`suwisa-backup` uses SQLite's online backup API, including committed WAL data. Do not simply copy the active database file while it is being written.

For the second disk set `BACKUP_DIR=/mnt/data/backup/suwisa` in `.env`, then:

```bash
sudo mkdir -p /mnt/data/backup/suwisa
sudo chown 1000:1000 /mnt/data/backup/suwisa
docker compose up -d
docker compose exec -T suwisa suwisa-backup /app/backups/manual.sqlite3
```

Daily crontab example for a user with Docker access:

```cron
15 3 * * * cd /opt/stacks/suwisa && /usr/bin/mountpoint -q /mnt/data && /usr/bin/docker compose exec -T suwisa suwisa-backup /app/backups/$(date +\%F).sqlite3
```

Keep another copy off this server. Backups contain private data. The bot does not prune backups automatically; choose retention and check restored copies with `PRAGMA integrity_check`.

## Monitoring

Health checks a recent gateway-ready timestamp. `restart: unless-stopped` covers process exit/reboot; an unhealthy result alone does not restart a container. Dockge shows health and logs. Uptime Kuma alerts can be added later; this repo does not configure them automatically.

Tokens and real receipts must stay outside Git and the Docker build context. Keep tokens only in `.env` on the runtime machine. Public CI needs no secrets.
