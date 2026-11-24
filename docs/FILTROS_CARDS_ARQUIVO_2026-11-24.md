# Filtros, navegação do card e arquivo de concluídas

## Comportamento

- Demandas, Meu trabalho e Calendário mantêm seus próprios filtros por perfil e aba do navegador. A seleção sobrevive à abertura do card, à consulta lateral, à troca de área e ao recarregamento. O Calendário também mantém o mês selecionado. Os filtros temporários usam `sessionStorage`; as visões salvas continuam sincronizadas no perfil.
- O card abre em uma visão de leitura com descrição, anexos e conversa. Um menu reúne as seções avançadas; outro oferece edição, arquivamento e exclusão conforme as permissões. A consulta lateral segue o mesmo padrão. A etapa e o responsável continuam na barra inferior.
- Concluir pela edição, última etapa ou Daily arquiva a demanda na mesma transação. A listagem operacional exclui concluídas, inclusive as anteriores à atualização. Importações Trello classificadas como concluídas também são arquivadas.
- Concluídas antigas sem `archived_at` são tratadas como arquivadas nas consultas. Não há alteração em massa nem migração destrutiva dos dados existentes.
- O arquivo administrativo inclui as concluídas anteriores. Restaurar uma concluída a reabre como Aguardando execução; mudar sua situação para ativa também a devolve à área operacional. O histórico de conclusão permanece disponível.
- Comentários, anexos, registros de etapas, apontamentos e indicadores permanecem no banco. Conclusão e arquivamento geram histórico e auditoria. Timers abertos precisam ser encerrados antes da conclusão, e um novo timer exige reabrir a demanda.

## Validação

- 222 testes de backend em PostgreSQL descartável local.
- 17 testes de frontend e compilação TypeScript/Vite.
- Ruff e verificação do diff.
- Conferência no Chrome com dados sintéticos: filtros por empresa, responsável e prioridade; retorno do card; consulta lateral; recarregamento; calendário; menus por teclado; conclusão, arquivo e restauração; larguras de 1440 e 390 px.

## Publicação

Validar primeiro em `http://127.0.0.1:18000`. A entrega não exige migração de esquema. Após a validação do preview pelo usuário, seguir o procedimento de backup, atualização e ativação do container descrito na documentação de publicação. Nenhuma base ou credencial de produção deve ser usada em testes.
