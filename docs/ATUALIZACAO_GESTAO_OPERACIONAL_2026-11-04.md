# Gestao de equipe, funcoes e workflows

Base: commit `523e850` da instalacao local no servidor `192.168.0.160`.

## Comportamento entregue

- Equipe: abrir uma pessoa para editar suas funcoes como principal ou substituto e suas excecoes por etapa.
- Workflows: botoes Responsaveis e Pessoas da funcao editam o mesmo cadastro central usado pela Equipe.
- Alteracoes em massa: previa dos modelos, demandas atuais e etapas futuras atingidas. Atribuicoes de card diferentes do padrao, etapas concluidas e prazos sao preservados.
- Exclusao de etapa: exige uma etapa de destino. Os planos dos cards sao atualizados, mantendo as versoes e visitas historicas.
- Exclusao de workflow: cards e categorias passam para o workflow padrao. Etapas de mesmo codigo sao correspondidas; sem correspondencia, o card vai para a primeira etapa ativa. O padrao da organizacao nao pode ser removido.
- Exclusao de pessoa: disponivel para administrador depois de suspender o acesso. Remove a credencial local, oculta o cadastro operacional, encerra timers da pessoa e redistribui responsabilidades pendentes para o substituto ou deixa sem responsavel. O identificador e o nome historicos sao preservados.
- Auditoria: registra a alteracao em massa, as transferencias de workflow, as exclusoes operacionais e as reatribuicoes de cards.

## Banco de dados

A migration `0020_operational_management` acrescenta `removed_at` a memberships, workflows e workflow_stages. A retirada operacional preserva registros referenciados por comentarios, apontamentos e versoes antigas. Nenhum card ou historico e apagado pela migration.

## Entrega na origem

Conforme definido, a entrega atualiza os arquivos na pasta compartilhada Y:, sem conexao SSH ou operacao de containers. O processo habitual de rebuild do servidor aplicara a migration aditiva 0020 antes de iniciar a API. O script de backup diario existente e as configuracoes locais permanecem preservados.

## Validacao funcional

1. Abrir Equipe, escolher uma pessoa e revisar suas funcoes e etapas.
2. Em Workflows, conferir principal e substituto e a previa de uma mudanca de responsabilidade.
3. Criar um fluxo de teste com cards sinteticos, exclui-lo e verificar a transferencia para o padrao.
4. Remover uma etapa de teste escolhendo o destino.
5. Suspender e excluir uma conta de teste; confirmar que comentarios e tempos continuam com o autor original.

## Versionamento

Na instalacao do servidor, origin aponta para GitLab e upstream para GitHub. Esta entrega usa uma branch codex para guardar a versao local no GitHub sem substituir automaticamente a branch main, que ainda pode acionar a antiga hospedagem no Render.

Os arquivos .env, backups e dados de migracao permanecem fora do versionamento.
