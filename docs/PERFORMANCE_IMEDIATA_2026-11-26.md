# Performance imediata pessoal — versão 6.1.3

## Navegação e escopo

Visão geral passa a ter duas subabas: **Visão geral** e **Performance**. A principal conserva seus indicadores e filtros. A subaba nova tem período próprio (hoje, ontem, semana, últimos sete dias ou intervalo personalizado de até 31 dias), dia de detalhe e configuração de alertas. Cada seleção fica separada por conta e área na sessão do navegador e é restaurada ao voltar de um card.

Performance é sempre pessoal, inclusive para administradores e coordenadores. A API não oferece seleção de pessoa ou equipe. Relatórios mantém seu escopo e permissões anteriores. O módulo e sua consulta são carregados apenas quando a subaba é aberta, com atualização a cada minuto e após eventos de alteração de timers.

## Indicadores e gráficos

- Tempo lançado no período e tempo de apontamentos ainda abertos, apresentado separadamente.
- Etapas avançadas e quantidade de cards distintos com entrega da pessoa.
- Cards desse conjunto que chegaram à conclusão final do workflow, mesmo que a conclusão ocorra depois do período selecionado.
- Retornos explícitos recebidos em etapas atribuídas à pessoa.
- Cadência diária/semanal, seleção de um dia e linha do tempo por demanda com inícios, pausas, retomadas, apontamentos manuais, avanços e retornos.
- Cobertura de registros no relógio: união dos intervalos, para não duplicar minutos quando dois timers estiverem simultâneos. O total apontado continua podendo somar esses intervalos.
- Lista acionável dos cards entregues, com acompanhamento de conclusão, filtro de situação e carregamento de mais itens.

Abrir um card concluído usa sua consulta individual, pois esses cards não pertencem à carteira ativa carregada na Visão geral. Itens na lixeira continuam preservando o histórico analítico, mas o botão de abertura é desabilitado.

## Tempo e qualidade do histórico

O sistema atual substitui `TimeEntry.started_at` ao retomar um timer. Portanto a cadência não pode ser reconstruída apenas por esse campo: usa os eventos nativos `TIMER_STARTED`, `TIMER_PAUSED`, `TIMER_RESUMED` e `TIMER_STOPPED`, associados ao identificador do apontamento e ao seu proprietário.

As novas movimentações incluem no payload o instante exato da ação; os eventos antigos continuam usando sua data de criação, sem reescrita. As pausas ficam fora dos intervalos e a divisão diária respeita o fuso do perfil, incluindo passagens pela meia-noite. Durações encerradas são distribuídas proporcionalmente aos intervalos conhecidos, preservando os minutos registrados pelo aplicativo; os arredondamentos do timer podem diferir ligeiramente do tempo corrido.

Apontamentos manuais e timers ajustados manualmente usam o intervalo informado, com tratamento visual distinto. Históricos sem rastreio suficiente preservam o total na data de encerramento do registro e ficam identificados como sem distribuição por horário; não geram uma faixa fictícia. Uma diferença relevante entre a duração armazenada e os intervalos disponíveis também impede presumir a distribuição. Em timers abertos sem histórico anterior, somente o início corrente comprovado é distribuído; os minutos acumulados sem data conhecida ficam separados na qualidade da base.

Apontamentos excluídos e tempos de outros usuários ou organizações ficam fora da leitura. Timers abertos são estimados até o instante da consulta e não são apresentados como tempo já lançado.

## Entregas e conclusão posterior

A autoria da entrega pertence ao responsável registrado na visita de etapa, não à pessoa que clicou. São considerados avanços reais comprovados, incluindo saltos manuais para frente; atribuições, dispensas de etapa e passagens meramente inferidas não criam entregas.

Várias etapas no mesmo card contam separadamente em **Etapas avançadas**, mas representam um único card na lista de entregas. O conjunto é selecionado pela data do avanço da pessoa. Depois acompanha-se a conclusão final comprovada até o momento da consulta. Isso difere do relatório por data de conclusão: um card entregue ontem pode aparecer como concluído ao revisar ontem, mesmo se chegou ao fim hoje. Reabrir o card suspende essa confirmação até uma nova conclusão.

## Aprovação e retrabalho

A elegibilidade considera etapas com revisão, aprovação ou validação posterior na definição da sua versão de workflow. Cada card, etapa e versão enviada no período conta uma vez. Uma saída real da etapa de avaliação por outro responsável comprova a aprovação; aprovar a própria etapa não é validação independente. Conclusão por simples mudança de status ou salto que dispense a avaliação não presume aprovação.

Um retorno explícito para a mesma etapa e pessoa após o envio classifica esse conjunto como retrabalho, mesmo que tenha sido reenviado e aprovado depois. **Aprovação sem retorno** e **Retrabalho** usam somente decisões comprovadas como denominador. As pendências aparecem separadas e não reduzem artificialmente essas taxas. O gráfico percentual também considera apenas as decisões, mantendo coerência com os números.

Retornos recebidos no período são listados com data e justificativa. O alerta distingue ajuste ainda na carteira atual de um retorno apenas registrado no histórico. Mudanças administrativas de responsabilidade e regressos sem evidência explícita não são atribuídos automaticamente como erro da pessoa.

## Alertas e referências pessoais

- Carteira atual com prazo vencido.
- Retorno recebido, com contexto do histórico e acesso ao card.
- Intervalos entre registros; por padrão, 90 minutos dentro de 08:00–18:00. A pessoa pode alterar o limite (30 a 240 minutos) e a faixa de acompanhamento nesta subaba. A leitura começa após o primeiro registro; para hoje, pode considerar o intervalo até o momento atual dentro da faixa configurada. Não presume tempo perdido antes do primeiro registro ou depois da faixa.
- Cards entregues que chegaram ao fim do fluxo.
- Falta de distribuição temporal comprovada ou ausência de apontamentos no período.
- Referência pessoal em formação ou comparações de tempo maduras.

Comparações exigem no mínimo **oito outros cards concluídos** nos 90 dias anteriores à conclusão analisada, da mesma pessoa, categoria, workflow e conjunto de etapas em que participou. O próprio card fica fora da amostra. A referência é a mediana dos tempos encerrados. A partir de 1,5 vez a referência aparece uma observação de tempo maior; até dois terços aparece uma de tempo menor. Não há classificação comparativa quando a amostra é insuficiente.

Esses sinais orientam a conferência dos registros e do contexto. Intervalos sem apontamento, tempo maior ou tempo menor não comprovam ausência de trabalho, qualidade ou produtividade. As observações são mostradas na subaba; não são disparos por e-mail ou notificações de sistema.

## Implementação e validação

- Nova API `GET /api/v1/performance/me`, com limite de 31 dias e validação do fuso, datas e faixa de acompanhamento.
- Consulta de dados por organização e pessoa, com carregamento de campos de tempo necessários, sem carregar notas pessoais para a análise.
- Consultas de histórico em quantidade fixa, sem uma consulta por card. O conteúdo do gráfico se restringe ao período solicitado; o histórico adicional sustenta as referências pessoais e a rastreabilidade das conclusões.
- Nenhuma nova tabela ou migration; a revisão do banco permanece `0023_analytics_alerts`. Dados e históricos anteriores não são recalculados por escrita.
- 270 testes de backend, incluindo banco PostgreSQL descartável, e 29 testes de frontend; compilação TypeScript/Vite, Ruff e tipagem dos módulos novos.
- Conferência no Chrome com dados sintéticos: quatro etapas, quatro cards, duas conclusões finais, um retorno, dois aprovados e um pendente, além de timers com pausa, paralelo e apontamentos manuais.
- Verificação de abertura de cards arquivados e retorno à mesma subaba, filtros independentes, teclado, períodos, atualização por timer, configuração de intervalo, paletas clara/escura e seis larguras de tela.

A entrega deve ser validada na prévia local antes de uma publicação posterior. A base local continua sendo o snapshot identificado em `docs/PREVIA_LOCAL.md`, sem equivalência automática com os dados atuais do servidor.
