#!/usr/bin/env bash
# Run on the production host after uploading overlay.tgz and overlay.sha256.
set -euo pipefail
exec 9>/opt/campfire/deploy.lock
flock -n 9
geo_old=$(readlink -f /opt/campfire/current)
test "$geo_old" = /opt/campfire/releases/metrics-window-20261106T092157Z
cd "$geo_old/backend"
export PYTHONPATH="$geo_old/backend"
/opt/campfire/venv/bin/python /tmp/campfire-director-idle.py
geo_stamp=$(date -u +%Y%m%dT%H%M%SZ)
geo_new=/opt/campfire/releases/geo-$geo_stamp
geo_backup=/opt/campfire/backups/before-geo-$geo_stamp
install -d -m 700 "$geo_backup"
printf '%s\n' "$geo_old" > "$geo_backup/previous-release.txt"
tar -czf "$geo_backup/release.tgz" -C "$geo_old" .
runuser -u postgres -- pg_dump -Fc campfire > "$geo_backup/database.dump"
pg_restore --list "$geo_backup/database.dump" > "$geo_backup/database-contents.txt"
cp /etc/nginx/conf.d/campfire.conf "$geo_backup/nginx.conf"
# Preserve config independently; never print or include it in the source archive.
cp -L /opt/campfire/shared/.env "$geo_backup/backend.env"
chmod 600 "$geo_backup/backend.env"
mkdir "$geo_new"
cp -a "$geo_old/." "$geo_new/"
tar -xzf /tmp/campfire-geo-overlay.tgz -C "$geo_new"
cd "$geo_new"
sha256sum -c /tmp/campfire-geo-overlay.sha256 > "$geo_backup/overlay-verified.txt"
chown -R campfire:campfire "$geo_new"
export PYTHONPATH="$geo_new/backend"
cd "$geo_new/backend"
# Rehearse upgrade, downgrade and re-upgrade on an empty private schema clone.
geo_testdb=campfire_geo_rehearsal
runuser -u postgres -- createdb -O campfire "$geo_testdb"
cleanup_rehearsal() { runuser -u postgres -- dropdb --if-exists "$geo_testdb"; }
trap cleanup_rehearsal EXIT
runuser -u postgres -- pg_dump --schema-only --no-owner campfire | runuser -u postgres -- psql -v ON_ERROR_STOP=1 "$geo_testdb" -c "SET ROLE campfire" -f - > "$geo_backup/rehearsal-schema.log"
runuser -u postgres -- psql "$geo_testdb" -v ON_ERROR_STOP=1 -c "INSERT INTO alembic_version(version_num) VALUES ('20261105_music_disabled');" > /dev/null
/opt/campfire/venv/bin/python /tmp/campfire-geo-rehearse.py > "$geo_backup/rehearsal.log" 2>&1
cleanup_rehearsal
trap - EXIT
cp /tmp/campfire-director-idle.py "$geo_backup/idle-check.py"
cat > "$geo_backup/rollback.sh" <<ROLLBACK
#!/usr/bin/env bash
set -euo pipefail
cd /opt/campfire/current/backend
PYTHONPATH=/opt/campfire/current/backend /opt/campfire/venv/bin/python '$geo_backup/idle-check.py'
systemctl stop campfire
ln -s '$geo_old' /opt/campfire/rollback-current
mv -Tf /opt/campfire/rollback-current /opt/campfire/current
cp '$geo_backup/nginx.conf' /etc/nginx/conf.d/campfire.conf
nginx -t
systemctl start campfire
systemctl reload nginx
# Additive GEO tables remain so new user data is retained. No destructive DB restore.
ROLLBACK
chmod 700 "$geo_backup/rollback.sh"
cd "$geo_old/backend"
PYTHONPATH="$geo_old/backend" /opt/campfire/venv/bin/python /tmp/campfire-director-idle.py
rollback_on_error() {
  geo_code=$?
  trap - ERR
  ln -s "$geo_old" /opt/campfire/failed-deploy-current
  mv -Tf /opt/campfire/failed-deploy-current /opt/campfire/current
  cp "$geo_backup/nginx.conf" /etc/nginx/conf.d/campfire.conf
  systemctl restart campfire
  nginx -t && systemctl reload nginx
  echo DEPLOY_FAILED_ROLLED_BACK
  exit "$geo_code"
}
trap rollback_on_error ERR
systemctl stop campfire
cd "$geo_new/backend"
PYTHONPATH="$geo_new/backend" /opt/campfire/venv/bin/alembic upgrade head > "$geo_backup/migration.log" 2>&1
ln -s "$geo_new" /opt/campfire/next-current
mv -Tf /opt/campfire/next-current /opt/campfire/current
cp "$geo_new/deploy/campfire.nginx.conf" /etc/nginx/conf.d/campfire.conf
nginx -t
systemctl start campfire
geo_healthy=0
for geo_attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8018/health > "$geo_backup/health-after.json"; then geo_healthy=1; break; fi
  sleep 1
done
test "$geo_healthy" = 1
systemctl reload nginx
for geo_attempt in {1..10}; do
  curl --fail --silent https://campfire.dawoai.com/ > "$geo_backup/home-after.html"
  if grep -q '发现企业与服务' "$geo_backup/home-after.html"; then break; fi
  sleep 1
done
grep -q '发现企业与服务' "$geo_backup/home-after.html"
curl --fail --silent https://campfire.dawoai.com/sitemap.xml > "$geo_backup/sitemap-after.xml"
systemctl is-active campfire
trap - ERR
printf 'DEPLOYED=%s\nBACKUP=%s\n' "$geo_new" "$geo_backup"
