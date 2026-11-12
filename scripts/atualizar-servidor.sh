#!/bin/sh
# Executar no host Docker, na pasta compartilhada do projeto.
set -eu
umask 077

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

docker compose version >/dev/null
docker compose config --quiet

# Optional workflow release: configuration stays on the host and enters via stdin.
if [ -n "${FM_WORKFLOW_CONFIG:-}" ]; then
  test -r "$FM_WORKFLOW_CONFIG"
  : "${FM_WORKFLOW_ACTOR:?defina o administrador em FM_WORKFLOW_ACTOR}"
fi

STAMP=$(date +%Y%m%d_%H%M%S)
DEST="$ROOT/backups/atualizacoes/$STAMP"
mkdir -p "$DEST"

OLD_IMAGE=$(docker compose images -q app | head -n 1)
if [ -z "$OLD_IMAGE" ]; then
  echo "O container app atual nao foi encontrado; atualizacao interrompida." >&2
  exit 1
fi
ROLLBACK_IMAGE="fluxo-marketing:antes-$STAMP"
docker image tag "$OLD_IMAGE" "$ROLLBACK_IMAGE"
printf '%s\n' "$ROLLBACK_IMAGE" > "$DEST/imagem-anterior.txt"
git -c safe.directory="$ROOT" rev-parse HEAD > "$DEST/versao-nova.txt"
if [ -r "$ROOT/.deployments/release.json" ]; then
  cp "$ROOT/.deployments/release.json" "$DEST/origem-codigo.json"
fi

echo "Criando e conferindo backup do banco atual do servidor..."
docker compose exec -T db pg_dump -U marketing -d marketing -Fc > "$DEST/banco.dump.tmp"
test -s "$DEST/banco.dump.tmp"
docker compose exec -T db pg_restore --list < "$DEST/banco.dump.tmp" >/dev/null
mv "$DEST/banco.dump.tmp" "$DEST/banco.dump"

echo "Criando e conferindo backup dos anexos atuais do servidor..."
docker compose run --rm --no-deps -T --entrypoint /bin/sh backup \
  -c 'tar -czf - -C /arquivos .' > "$DEST/anexos.tar.gz.tmp"
test -s "$DEST/anexos.tar.gz.tmp"
tar -tzf "$DEST/anexos.tar.gz.tmp" >/dev/null
mv "$DEST/anexos.tar.gz.tmp" "$DEST/anexos.tar.gz"

echo "Recompilando a aplicacao; o servico atual continua ativo durante o build..."
docker compose build app

if [ -n "${FM_WORKFLOW_CONFIG:-}" ]; then
  echo "Conferindo os vinculos no banco atual do servidor..."
  docker compose run --rm --no-deps -T --entrypoint python app \
    -m app.workflow_simplification_cli \
    --organization "${FM_WORKFLOW_ORGANIZATION:-marketing}" \
    --actor "$FM_WORKFLOW_ACTOR" --config - \
    < "$FM_WORKFLOW_CONFIG" > "$DEST/workflows-simulacao.json"

  echo "Aplicando os vinculos e desativando checklists automaticos com auditoria..."
  docker compose run --rm --no-deps -T --entrypoint python app \
    -m app.workflow_simplification_cli \
    --organization "${FM_WORKFLOW_ORGANIZATION:-marketing}" \
    --actor "$FM_WORKFLOW_ACTOR" --config - --apply \
    < "$FM_WORKFLOW_CONFIG" > "$DEST/workflows-aplicados.json"
fi

echo "Ativando somente app, preservando banco e volumes..."
docker compose up -d --no-deps --no-build --force-recreate --wait --wait-timeout 240 app
docker compose exec -T app python -c \
  "import urllib.request; assert urllib.request.urlopen('http://localhost:8000/health', timeout=10).status == 200; print('Saude da aplicacao: OK')"

printf '\nAtualizacao ativada. Backup desta operacao: %s\n' "$DEST"
printf 'Imagem anterior preservada: %s\n' "$ROLLBACK_IMAGE"
