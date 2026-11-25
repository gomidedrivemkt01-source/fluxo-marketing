# Relatórios de participação e alertas — 25/11/2026

Entrega preparada exclusivamente para prévia. A publicação no servidor depende da validação visual do usuário. Nenhum arquivo ou banco de produção deve ser alterado nesta etapa.

## Correção de layout

Os botões da lista de aprovações misturavam grid de tamanho automático com textos flexíveis cujo tamanho mínimo era o conteúdo. Títulos longos ampliavam a coluna e transbordavam o painel. A correção usa `minmax(0, 1fr)`, permite o encolhimento dos itens e limita títulos, marcas e responsáveis. O título completo permanece no atributo `title` e na abertura do card. A rolagem horizontal da página não foi ocultada para mascarar o problema.

## Dados disponíveis e uso analítico

| Fonte | O que comprova | Uso nesta entrega |
| --- | --- | --- |
| Demand | Estado atual, responsável atual, marca, categoria, prazo, criação e arquivamento | Carteira, risco de prazo, atenção e ciclo completo |
| DemandStageVisit | Pessoa atribuída à passagem, entrada, saída, versão, tipo de movimento e indicação de inferência | Participação, avanço, permanência e retornos |
| WorkflowVersion | Ordem imutável das etapas e parâmetros daquela versão | Comprovação de etapa final e interpretação de movimentos antigos |
| DemandUpdate | Evento de conclusão, data e origem da movimentação | Data de confirmação final; distinção entre finalizar o fluxo e apenas mudar o status |
| DemandStageInstance | Planejamento mutável de responsável e prazo por etapa | Contexto de prazo congelado nas próximas saídas; isoladamente não comprova entrega |
| TimeEntry | Apontamentos por pessoa, categoria e período, origem e estado do timer | Tempo encerrado e distribuição por categoria; timers abertos ficam separados |
| Company / DemandCategory / UserProfile | Identificação e classificação | Leitura por pessoa, categoria e marca nas demandas de atenção |
| Checklist, briefing, comentários, anexos, auditoria e importações | Conteúdo, validações e rastreabilidade | Preservados; quantidade desses registros não representa produtividade nem entrega |
| DemandStateInterval | Intervalos de estado quando registrados | Sem gráfico de espera nesta entrega: a cópia disponível não oferece cobertura suficiente |

Não se presume capacidade contratada, horas disponíveis, utilização da pessoa ou produtividade a partir do tempo apontado. Timers simultâneos podem sobrepor intervalos. Permanência em etapa mede horas corridas, não horas trabalhadas.

## Regra das entregas

1. Uma saída real para frente pertence ao responsável registrado na visita de etapa. O autor do clique não recebe a entrega por executar a ação.
2. Várias etapas, repetições ou retornos no mesmo card geram no máximo uma contribuição confirmada por pessoa e card.
3. O avanço fica visível como progresso. A confirmação depende de o card estar concluído e de existir evidência de saída da etapa final de sua versão de workflow.
4. A confirmação usa a data da conclusão final. Uma pessoa pode receber crédito no período mesmo tendo realizado sua etapa antes dele.
5. “Aguardando conclusão” mostra contribuições avançadas no período que continuam sem confirmação final no estado atual. Esse conjunto e o de confirmações têm coortes diferentes: não há taxa artificial de conversão entre os dois.
6. Reabrir um card suspende a confirmação enquanto ele estiver ativo. Reencerrá-lo não duplica a pessoa no mesmo card; a nova conclusão determina seu período. O relatório usa o histórico disponível e o estado atual, não uma fotografia retroativa imutável.
7. “Cards concluídos” conta cards distintos com data de conclusão comprovada. A soma de contribuições da equipe pode ser maior: várias pessoas podem ter contribuído para o mesmo card. Uma conclusão por simples mudança de status pode aparecer como card encerrado, mas não confirma entregas individuais sem evidência final de workflow.
8. Saídas ainda não comprovadas de passagens inferidas, transferências de responsável, saltos com ação explícita de dispensa e retornos não geram crédito de avanço. Uma seleção manual comprovadamente para uma etapa posterior conta como avanço da etapa de origem.

Movimentos antigos são interpretados por evidências já existentes: próxima entrada real compatível, ordem da versão do workflow e evento nativo de conclusão. Uma passagem antiga com entrada inferida pode receber crédito quando sua saída passa a ser efetivamente registrada pelo usuário nesta versão; sua permanência continua fora do cálculo porque o início é incerto. Nenhum histórico é reescrito. A partir desta versão, as saídas passam a registrar a decisão e os parâmetros históricos de nome, SLA e prazo. Taxas de SLA e pontualidade usam somente parâmetros congelados; ausência de base aparece como “Sem base”, nunca como zero ou sucesso presumido.

## Painéis

- Quatro indicadores: contribuições confirmadas, contribuições aguardando fim, cards concluídos e tempo encerrado.
- Barras por dia, semana ou mês para comparar cards concluídos e contribuições confirmadas, com unidades distintas.
- Barras de risco para prazos vencidos, próximos, distantes e ausentes na carteira atual.
- Etapas ordenadas pela permanência P90, com mediana, número de saídas, retornos e SLA quando houver base histórica.
- Rosca e legenda de tempo real encerrado por categoria, incluindo agrupamento das demais categorias sem perder seu total.
- Tabela de pessoas com entregas, avanços, carga atual, atraso e tempo.
- Ciclo mediano e P90, pontualidade com quantidade de prazos medidos e cards distintos com avanços.
- Lista acionável das primeiras 30 demandas que precisam de atenção; abrir a demanda mantém os filtros do relatório.
- Explicação expansível da cobertura e das limitações dos dados.

Período personalizado e seleção por pessoa permanecem disponíveis. Colaboradores e visualizadores recebem apenas seu próprio escopo, imposto pela API. Administradores e coordenadores podem analisar equipe ou pessoa. Dados de cards arquivados e históricos preservados continuam compondo os indicadores.

## Alertas

`Gestão → Configurações → Alertas`, disponível somente ao administrador:

- Ativar ou desativar os avisos.
- Definir limite de 1 a 90 dias corridos, padrão 7.
- Escolher avisos de prazo próximo, prazo vencido e aprovação pendente.
- Incluir responsáveis de passagens reais anteriores, além do responsável atual.

Prazo próximo significa `0 <= prazo - agora < limite`. O limite exato de sete dias ainda não dispara o aviso. Prazo vencido tem prioridade e cada card aparece uma vez com os motivos combinados. Aprovações são identificadas pelo estado ou nome da etapa atual. Concluídos, arquivados e excluídos não geram alertas.

Os avisos aparecem no sino, atualizam a cada 60 segundos e ao abrir o painel, e permanecem enquanto a situação estiver pendente. A lista permite carregar os próximos avisos. O salvamento administrativo atualiza a prévia imediatamente e registra antes/depois na auditoria, com proteção contra edição concorrente. Não há disparo por e-mail ou push. Na visão geral, prazos próximos recebem destaque e filtro próprio; a configuração desativada remove esse destaque preventivo.

## Migração e ativação

`0023_analytics_alerts` é aditiva: cria a tabela de políticas e dois índices de consulta. Não limpa demandas, não muda atribuições e não recalcula nem remove históricos. A política padrão funciona sem inserir registros até o primeiro salvamento administrativo.

APIs novas: `GET /reports/analytics`, `GET /notifications/policy`, `PUT /notifications/policy`, `GET /notifications/inbox`, todas sob `/api/v1`. O endpoint operacional anterior permanece para compatibilidade.

Depois da aprovação da prévia, a ativação futura exige backup, migração Alembic e recompilação/reinício da aplicação no servidor. Copiar apenas o frontend não ativa os novos indicadores e alertas.

## Validação

- 244 testes de backend, incluindo PostgreSQL descartável com a migração nova.
- 23 testes de frontend; build TypeScript/Vite aprovado.
- Ruff e tipagem estrita dos três módulos novos de backend aprovados.
- Chrome com dados sintéticos isolados: conclusão real de workflow, progresso pendente, apontamentos, período personalizado, filtro por pessoa, persistência de alertas e sino.
- Títulos de 300 caracteres com e sem espaços, marcas e responsáveis extensos, limites dos filhos dos painéis e largura da página verificados em 1920, 1440, 1024, 768, 390 e 320 px.
- Inspeção visual nas paletas clara e escura. A prévia do usuário usa o snapshot local identificado em `docs/PREVIA_LOCAL.md`; não é uma réplica em tempo real da produção.
