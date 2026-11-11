# Timers paralelos, demandas em massa e ciência de pendências

Entrega para a prévia local `http://127.0.0.1:18000`, preparada sobre `aabb6be`. O servidor da empresa não recebe alterações durante esta validação.

## Dois timers

- Cada pessoa pode manter até dois timers abertos, em demandas diferentes. Pausados também ocupam uma das duas posições; concluir um apontamento libera a posição.
- Iniciar novamente o mesmo card reaproveita seu timer e retoma um apontamento pausado. Não cria dois apontamentos simultâneos da mesma pessoa para o mesmo card.
- Os dois balões mostram card, relógio, play/pause, concluir e abrir card. Continuam acessíveis entre páginas e ficam acima do rodapé fixo dos cards.
- Limite e unicidade são impostos na API e no PostgreSQL, inclusive com cliques concorrentes ou abas distintas. Cada pessoa tem suas próprias posições.
- Os tempos são reais por demanda e podem se sobrepor. A soma dos apontamentos pode superar o tempo exclusivo de uma pessoa; não representa horas sem sobreposição.

## Demandas em massa

A aba do menu Trabalho está disponível aos perfis ativos. Administradores, coordenadores e colaboradores com `demands:write` ou `demands:work` podem enviar e criar lotes. Perfis somente de leitura podem baixar o modelo; não recebem nova permissão de escrita.

Fluxo: **Baixar modelo para o chat → estruturar os materiais no chat → enviar JSON → Validar e revisar → conferir cada card → marcar confirmação → Criar demandas**.

O arquivo baixado é um JSON de entrada válido. Contém `guide` com instruções para o chat, empresas, categorias, briefing de cada categoria, workflows publicados com etapas e pessoas ativas da própria organização. O guia pode ser omitido no arquivo final. O JSON Schema está disponível como recurso adicional.

Contrato `fluxo.demands.v1`, até 200 cards / 5 MB por lote:

```json
{
  "schemaVersion": "fluxo.demands.v1",
  "batchId": "marca-editorial-2026-12-v1",
  "cards": [
    {
      "externalId": "marca-2026-12-post-001",
      "title": "Título do material",
      "description": "Objetivo, conteúdo e orientações",
      "companyCode": null,
      "categoryCode": null,
      "workflowCode": null,
      "stageCode": null,
      "assigneeEmail": null,
      "priority": "NORMAL",
      "deadlineAt": "2026-12-10T17:00:00-03:00",
      "briefing": {},
      "checklist": ["Revisar o texto", "Preparar a mídia"]
    }
  ]
}
```

- Usar os códigos exatos do catálogo incluído no modelo. Etapa precisa pertencer ao workflow; e-mail precisa ser de uma pessoa ativa da organização.
- `workflowCode` ausente/null usa o padrão da categoria, ou o padrão da plataforma quando não há categoria. `stageCode` ausente/null usa a primeira etapa.
- `assigneeEmail` omitido herda a função da etapa; `null` deixa sem responsável; e-mail define uma pessoa específica. A prévia mostra a pessoa que será aplicada.
- Datas usam ISO 8601 com fuso explícito. `null` mantém sem prazo, sem inferir datas. Prioridades: LOW, NORMAL, HIGH, URGENT.
- `briefing` usa as chaves reais da categoria. `checklist` acrescenta tarefas personalizadas; não conclui os itens obrigatórios do workflow.
- `externalId` é estável e único na organização. Reenviar o mesmo material, mesmo em outro lote, não duplica nem sobrescreve o card existente. A chave é preservada também para cards arquivados/na lixeira.
- Repetir o mesmo `batchId` e conteúdo devolve o resultado anterior. Conteúdo diferente exige outra versão de `batchId`; os mesmos materiais mantêm seu `externalId`.
- Nenhum card é criado na revisão. Aplicar exige a impressão da prévia atual. Mudança de arquivo, cadastro ou etapa exige revisar novamente. O lote é transacional: erros impedem a criação parcial.
- Histórico de lotes: últimos 50; colaborador consulta os próprios, gestão consulta a organização. O histórico da demanda identifica lote, chave externa e autor.

## Erros e alertas

Os formulários mostram resumo dos campos pendentes, asterisco no campo e explicação. O resumo permite focar o campo correspondente. Erros de formato, referências indisponíveis, autenticação, permissão e conflitos de revisão continuam exigindo correção; não podem ser contornados por ciência.

Alertas de negócio permitem **Corrigir campos** ou marcar a ciência e **Seguir mesmo assim**. O checkbox começa desmarcado. Abrange prazo final vencido quando alterado, descrição editada acima de 5.000 caracteres, prazo de etapa posterior ao final, briefing obrigatório incompleto, checklist obrigatório incompleto e retorno sem justificativa detalhada. Na última situação, o chat também recebe um aviso explícito de retorno sem detalhes.

O servidor reavalia os alertas no reenvio. Apenas os códigos realmente pendentes e aceitos são registrados. `WARNING_ACKNOWLEDGED` e o evento de auditoria guardam autor, data, ação, revisão e descrição das pendências na mesma transação da alteração. Cancelar não salva a operação. Um timer aberto ainda precisa ser encerrado antes de trocar a etapa para preservar o apontamento correto.

A edição lateral agora envia o workflow atual, evitando reclassificar o card ao editar o prazo. Descrições antigas de até 50.000 caracteres são preservadas numa simples troca de data; uma edição que exceda 5.000 solicita ciência.

## Persistência e testes

Migration `0022_parallel_timers_bulk`: acrescenta a posição do timer e índices únicos por pessoa/posição e pessoa/card, além das tabelas de lotes/chaves. Os registros existentes recebem posição 1, sem alteração de duração. O downgrade recusa apagar rastreabilidade ou remover o suporte quando há dois timers abertos.

Validação: 210 testes de backend com PostgreSQL descartável, 15 testes de frontend, build, Ruff e checagem de tipos dos módulos alterados. Conferência de navegador em conta sintética: dois timers, terceiro bloqueado, pausa/retomada independente, download do modelo, revisão/confirmação, criação de dois cards, reenvio sem duplicação, ciência desmarcada inicialmente, gravação confirmada e erro de campo visível. Tela de importação conferida em 1366px e 390px sem transbordamento horizontal ou erros de JavaScript.

A ativação local cria backup do banco em `.preview/backups/` e confere as contagens existentes depois da migration. Dados e credenciais da prévia e dos testes não entram no GitHub.
