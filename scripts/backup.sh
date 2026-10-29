#!/bin/sh
# Backup diário do banco (pg_dump formato custom) e dos anexos (tar.gz), mantendo os últimos BACKUP_DIAS dias.
# Restaurar banco:   docker compose exec -T db pg_restore -U marketing -d marketing --clean --if-exists < backups/fluxo_AAAA-MM-DD_HHMM.dump
# Restaurar anexos:  docker compose run --rm --no-deps -v "$PWD/backups:/backups:ro" app sh -c 'tar -xzf /backups/fluxo_arquivos_AAAA-MM-DD_HHMM.tar.gz -C /app/storage'
set -eu
HORA="${BACKUP_HORA:-23}"; DIAS="${BACKUP_DIAS:-30}"
fazer() {
  sufixo="$(date +%F_%H%M)"
  f="/backups/fluxo_${sufixo}.dump"
  if pg_dump -Fc -f "$f.tmp"; then mv "$f.tmp" "$f"; echo "$(date '+%F %T') backup do banco ok: $f ($(du -h "$f" | cut -f1))"
  else rm -f "$f.tmp"; echo "$(date '+%F %T') ERRO no backup do banco" >&2; fi
  a="/backups/fluxo_arquivos_${sufixo}.tar.gz"
  if tar -czf "$a.tmp" -C /arquivos .; then mv "$a.tmp" "$a"; echo "$(date '+%F %T') backup dos anexos ok: $a ($(du -h "$a" | cut -f1))"
  else rm -f "$a.tmp"; echo "$(date '+%F %T') ERRO no backup dos anexos" >&2; fi
  find /backups -name 'fluxo_*' -mtime +"$DIAS" -delete
}
[ "${1:-}" = "agora" ] && { fazer; exit 0; }
echo "Backup diário às ${HORA}h, retenção de ${DIAS} dias"
ultimo=""
while true; do
  h=$(date +%H | sed "s/^0//"); d=$(date +%F)
  if [ "$h" -eq "$HORA" ] 2>/dev/null && [ "$ultimo" != "$d" ]; then fazer; ultimo="$d"; fi
  sleep 300
done
