# Backup and Restore (N-05, Implemented)

Daily logical backups of the PostgreSQL database, an off-server copy in Google Drive, and a two-step-confirmed restore are implemented. Design decisions are recorded in `docs/DECISIONS.md` (D-09); the feature spec is `docs/specs/db-backup.md`.

## How It Works

- **Host cron (primary):** `scripts/backup.py` runs `pg_dump -Fc` inside the Compose `db` service, writes `bookzma-YYYY-MM-DD-HHMMSS.dump` to the host backup folder, keeps only the newest local file, and optionally uploads to Google Drive via `rclone`, keeping 14 daily generations there.
- **Admin panel (on demand):** the bot's admin panel (`/admin` → «💾 بکاپ») shows the latest local backup, runs an on-demand backup through `services/backup.py` (`pg_dump` over TCP to the `db` service, from inside the bot container), and can restore a local backup after an explicit warning plus a typed confirmation word («بازیابی»).
- Both paths write to the same folder: `BOOKZMA_BACKUP_DIR` on the host, bind-mounted to `/backups` in the bot container. Backups must never be placed inside the repository or the database volume; the service refuses a destination inside the source tree.
- Files are created with mode `600` (folder `700`). The bot container needs write access, so the host folder must be writable by UID 10001.
- The Docker image installs `postgresql-client` (Debian trixie ships client 17 ≥ server 16). Keep the client version at or above the server major version.
- Failure detection: command exit status, non-empty output file, subprocess timeouts (dump 15 min, restore 30 min), and structured application logs. A failed or empty dump deletes the partial file and reports a generic error to the admin; details go to the server log only. Nothing sensitive (tokens, passwords, DSNs) is ever logged.

## One-Time Setup (Owner)

1. Choose a folder outside the repository, e.g. `sudo mkdir -p /var/backups/bookzma && sudo chown 10001:10001 /var/backups/bookzma`.
2. Add to `.env`: `BOOKZMA_BACKUP_DIR=/var/backups/bookzma` (required by Compose) and optionally `BACKUP_KEEP_LOCAL=1`.
3. Install `rclone` on the host and configure Google Drive once: `rclone config` → create a remote (e.g. `gdrive:`). Keep the rclone config private (`~/.config/rclone/rclone.conf`, mode `600`).
4. Install the cron entry (adjust paths):
   ```
   30 3 * * * python3 /path/to/BOOKzMA/scripts/backup.py \
       --project /path/to/BOOKzMA --dest /var/backups/bookzma \
       --rclone gdrive:bookzma-backups >> /var/log/bookzma-backup.log 2>&1
   ```
5. Rebuild/restart: `docker compose up -d --build` (the image gains `postgresql-client` and the bot gains the `/backups` mount).
6. Run one manual backup and verify: the cron command without cron, or the admin panel's «بکاپ جدید» button. Then check the file exists with `pg_restore --list`.

## Restore Rehearsal (Run Periodically)

Never rehearse against production and never overwrite the only backup.

```sh
docker run --rm -d --name bookzma-restore-test \
    -e POSTGRES_PASSWORD=testonly postgres:16-alpine
python3 scripts/restore.py --dump /var/backups/bookzma/bookzma-YYYY-MM-DD-HHMMSS.dump \
    --container bookzma-restore-test --db-user postgres --db-name postgres
docker exec -it bookzma-restore-test psql -U postgres -d postgres -c '\dt'
docker stop bookzma-restore-test
```

Record the date, elapsed time, and result of each rehearsal.

## Real Restore

Prefer the admin panel (two-step confirmation) or `scripts/restore.py --main-db` with its typed confirmation. After a real restore, run `docker compose restart bot` so pool connections and in-process state pick up the restored data.

## Known Limitations

- Data from account deletions (N-04) may persist inside older backups until those backups rotate out; this is disclosed in the in-bot deletion flow.
- Restoring an older backup reverts everything recorded after it; tombstones recorded after the backup are not automatically reapplied (tracked as L-02).
- Backups are not encrypted at rest; encryption and further off-site policy are future work (L-02).
- Admin-panel backup management covers local files only; Google Drive rotation is host-side.
