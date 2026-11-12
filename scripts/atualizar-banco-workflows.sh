#!/bin/sh
# Executar no host Docker. Usa a imagem atual; nao recompila nem recria servicos.
set -eu
umask 077

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
CONFIG=${FM_WORKFLOW_CONFIG:-$ROOT/.deployments/workflows/configuration.json}
: "${FM_WORKFLOW_ACTOR:?defina o administrador em FM_WORKFLOW_ACTOR}"
ORGANIZATION=${FM_WORKFLOW_ORGANIZATION:-marketing}
test -r "$CONFIG"
docker compose config --quiet
docker compose exec -T app python -c 'import app.workflow_simplification_cli'

STAMP=$(date +%Y%m%d_%H%M%S)
DEST="$ROOT/backups/atualizacoes/workflows-banco-$STAMP"
mkdir -p "$ROOT/backups/atualizacoes"
mkdir "$DEST"
echo "Criando e conferindo backup do banco do servidor..."
docker compose exec -T db pg_dump -U marketing -d marketing -Fc > "$DEST/banco.dump.tmp"
test -s "$DEST/banco.dump.tmp"
docker compose exec -T db pg_restore --list < "$DEST/banco.dump.tmp" >/dev/null
mv "$DEST/banco.dump.tmp" "$DEST/banco.dump"

echo "Simulando a configuracao no banco atual..."
docker compose exec -T app python -m app.workflow_simplification_cli \
  --organization "$ORGANIZATION" --actor "$FM_WORKFLOW_ACTOR" --config - \
  < "$CONFIG" > "$DEST/workflows-simulacao.json"

echo "Aplicando os ajustes com auditoria..."
docker compose exec -T app python -m app.workflow_simplification_cli \
  --organization "$ORGANIZATION" --actor "$FM_WORKFLOW_ACTOR" --config - --apply \
  < "$CONFIG" > "$DEST/workflows-aplicados.json"

echo "Conferindo se ainda existe alguma configuracao pendente..."
docker compose exec -T app python -m app.workflow_simplification_cli \
  --organization "$ORGANIZATION" --actor "$FM_WORKFLOW_ACTOR" --config - \
  < "$CONFIG" > "$DEST/workflows-verificacao.json"

REPORT="$ROOT/.deployments/workflows/verification.json"
mkdir -p "$(dirname -- "$REPORT")"
TEMP_REPORT="$REPORT.$STAMP.tmp"
docker compose exec -T app python -c '
import json, sys
from datetime import datetime, timezone
result = json.load(sys.stdin)
assert not result["createdFunctions"], "Ainda ha funcoes a criar."
assert not result["renamedFunctions"], "Ainda ha nomes a ajustar."
assert result["checklistsDisabled"] == 0, "Ainda ha checklists automaticos ativos."
assert not result["responsibilities"], "Ainda ha responsabilidades a atualizar."
print(json.dumps({"databaseConfigurationVerified": True,
    "configuredFunctions": result["configuredFunctions"],
    "linkedStages": result["linkedStages"], "activeAutomaticChecklists": 0,
    "verifiedAt": datetime.now(timezone.utc).isoformat()}, indent=2))
' < "$DEST/workflows-verificacao.json" > "$TEMP_REPORT"
# Somente o resumo sem nomes/segredos fica legivel pelo compartilhamento.
chmod 644 "$TEMP_REPORT"
mv "$TEMP_REPORT" "$REPORT"
printf '\nConfiguracao do banco aplicada e verificada.\nBackup: %s\nResumo: %s\n' "$DEST" "$REPORT"
