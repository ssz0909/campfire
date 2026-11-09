#!/usr/bin/env bash
# Upload /tmp/campfire-llms-{overlay.tgz,overlay.sha256,baseline.sha256} first.
set -euo pipefail
exec 9>/opt/campfire/deploy.lock
flock -n 9
llms_old=$(readlink -f /opt/campfire/current)
test "$llms_old" = /opt/campfire/releases/geo-20261109T114819Z
cd "$llms_old"
sha256sum -c /tmp/campfire-llms-baseline.sha256 > /dev/null
cd backend
PYTHONPATH=. /opt/campfire/venv/bin/python /tmp/campfire-director-idle.py
llms_stamp=$(date -u +%Y%m%dT%H%M%SZ)
llms_new=/opt/campfire/releases/llms-$llms_stamp
llms_backup=/opt/campfire/backups/before-llms-$llms_stamp
install -d -m 700 "$llms_backup"
tar -czf "$llms_backup/release.tgz" -C "$llms_old" .
runuser -u postgres -- pg_dump -Fc campfire > "$llms_backup/database.dump"
pg_restore --list "$llms_backup/database.dump" > "$llms_backup/database-contents.txt"
cp /etc/nginx/conf.d/campfire.conf "$llms_backup/nginx.conf"
printf '%s\n' "$llms_old" > "$llms_backup/previous-release.txt"
mkdir "$llms_new"
cp -a "$llms_old/." "$llms_new/"
tar -xzf /tmp/campfire-llms-overlay.tgz -C "$llms_new"
cd "$llms_new"
sha256sum -c /tmp/campfire-llms-overlay.sha256 > "$llms_backup/overlay-verified.txt"
chown -R campfire:campfire "$llms_new"
cp /tmp/campfire-director-idle.py "$llms_backup/idle-check.py"
cat > "$llms_backup/rollback.sh" <<ROLLBACK
#!/usr/bin/env bash
set -euo pipefail
cd /opt/campfire/current/backend
PYTHONPATH=. /opt/campfire/venv/bin/python '$llms_backup/idle-check.py'
systemctl stop campfire
ln -s '$llms_old' /opt/campfire/rollback-current
mv -Tf /opt/campfire/rollback-current /opt/campfire/current
cp '$llms_backup/nginx.conf' /etc/nginx/conf.d/campfire.conf
nginx -t
systemctl start campfire
systemctl reload nginx
ROLLBACK
chmod 700 "$llms_backup/rollback.sh"
rollback_on_error() {
  llms_code=$?
  trap - ERR
  ln -s "$llms_old" /opt/campfire/failed-deploy-current
  mv -Tf /opt/campfire/failed-deploy-current /opt/campfire/current
  cp "$llms_backup/nginx.conf" /etc/nginx/conf.d/campfire.conf
  systemctl restart campfire
  nginx -t && systemctl reload nginx
  echo DEPLOY_FAILED_ROLLED_BACK
  exit "$llms_code"
}
trap rollback_on_error ERR
cd "$llms_old/backend"
PYTHONPATH=. /opt/campfire/venv/bin/python /tmp/campfire-director-idle.py
systemctl stop campfire
ln -s "$llms_new" /opt/campfire/next-current
mv -Tf /opt/campfire/next-current /opt/campfire/current
cp "$llms_new/deploy/campfire.nginx.conf" /etc/nginx/conf.d/campfire.conf
nginx -t
systemctl start campfire
llms_healthy=0
for llms_attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8018/health > "$llms_backup/health.json"; then llms_healthy=1; break; fi
  sleep 1
done
test "$llms_healthy" = 1
systemctl reload nginx
for llms_attempt in {1..10}; do
  curl --fail --silent https://campfire.dawoai.com/llms.txt > "$llms_backup/llms.txt"
  if grep -q '^# 营火AI' "$llms_backup/llms.txt"; then break; fi
  sleep 1
done
grep -q '^# 营火AI' "$llms_backup/llms.txt"
curl --fail --silent https://campfire.dawoai.com/llms/companies/1.txt > "$llms_backup/directory.txt"
grep -q '^# 营火AI公开企业目录' "$llms_backup/directory.txt"
systemctl is-active campfire
trap - ERR
printf 'DEPLOYED=%s\nBACKUP=%s\n' "$llms_new" "$llms_backup"
