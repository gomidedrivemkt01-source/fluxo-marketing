# Fluxo Marketing

Fundação da plataforma interna de gestão e inteligência operacional do Marketing.

O MVP entrega autenticação por e-mail e senha com código, recuperação de senha, aprovação administrativa, perfis de acesso, criação e edição manual de demandas, responsáveis, workflows reutilizáveis, visões pessoais em Kanban e lista, empresas, categorias, briefings configuráveis, checklists por etapa e por card, comentários, histórico, timer, arquivos privados, perfil com foto, auditoria, relatórios operacionais, importação assistida de Dailys e migração controlada de quadros do Trello.

A criação manual é a entrada principal da operação. **Início** funciona como agenda pessoal e separa as entregas em atrasadas, hoje, amanhã e datas futuras. **Meu trabalho** permite criar, ordenar e colorir colunas pessoais em Kanban ou lista sem alterar o workflow compartilhado. Ao filtrar um responsável, a equipe vê a organização escolhida por essa pessoa; ao combinar responsáveis, a plataforma usa uma lista única.

Administradores e coordenadores mantêm uma biblioteca de workflows na área **Workflows**. Cada modelo possui suas próprias etapas, checklists, responsáveis padrão e durações esperadas. Uma categoria pode apontar para seu workflow padrão, e um card pode substituir esse modelo quando precisar de um fluxo específico. A migração inicial preserva o fluxo existente como **Fluxo padrão**.

Cada demanda guarda a versão imutável do workflow usada no momento da criação ou da troca explícita de fluxo. Alterações posteriores no modelo passam a valer para novos cards sem modificar retroativamente as demandas em andamento. A aba **Workflow** combina o histórico real com a agenda de cada etapa, permite ajustar prazo e previsão e destaca etapas vencidas ou em risco. As ações **Retornar**, **Pular** e **Avançar** registram o handoff; a saída é bloqueada enquanto houver timer aberto e o avanço também exige os itens obrigatórios do checklist. Uma versão compacta dessa timeline aparece na visão geral do card.

Na área **Categorias**, a administração combina workflow e modelo de briefing. Dentro do card, a visão geral reúne dados essenciais, timer, checklist rápido e uma lateral que alterna entre comentários e histórico. As abas avançadas preservam o briefing completo, workflow, checklist, arquivos, atividade e tempo. O timer pode ser iniciado, pausado, retomado e concluído; a aba de tempo mantém o ajuste manual e o histórico da equipe.

O upload de uma Daily é um recurso complementar na área de Inteligência e nunca altera cards automaticamente. A aplicação valida o JSON, abre cada item para revisão e exige uma escolha explícita: associar a um card existente, criar um card ou ignorar. As atualizações são aplicadas em uma única operação somente depois que todos os itens forem revisados. Revisões interrompidas ficam disponíveis para continuação.

## Plano de execução ativo

- **Marco 1 — Fundação e acesso:** autenticação, aprovação, perfis, cadastros, auditoria e infraestrutura online concluídos.
- **Marco 2 — Card operacional:** criação manual, briefing, checklist, comentários, histórico, arquivos privados e timer concluídos.
- **Marco 3 — Fluxo e foco pessoal:** agenda Todoist, Kanban pessoal, biblioteca de workflows, versões imutáveis, agenda por etapa, handoffs validados e alertas de risco concluídos nesta base.
- **Marco 4 — Relatórios operacionais:** primeira visão executiva concluída com períodos rápidos ou personalizados, indicadores de prazo, volume, tempo apontado, esforço previsto e gargalos por empresa, categoria, responsável e etapa. Administradores e coordenadores alternam entre o overview da equipe e relatórios individuais; colaboradores e visualizadores recebem somente o próprio relatório, com a restrição aplicada também na API.
- **Marco 5 — Governança de dados:** área administrativa para validar, importar e exportar JSON compatível com Trello; vínculo estável por cartão para impedir duplicações; histórico de lotes com reversão; versões automáticas das demandas; restauração de itens arquivados; e retenção bimestral reversível de demandas concluídas, preservando tempos e indicadores.
- **Marco 6 — Histórico, indicadores e distribuição (em andamento):** relatórios com tendência temporal de entradas, conclusões e horas apontadas; leitura de carteira prevista versus tempo realizado por pessoa; e tempo real por etapa com aderência ao SLA em horas corridas e ciclos de retorno.
- **Próximo incremento:** filtros persistentes dos relatórios, lead/cycle time, tempo bloqueado, aprovação na primeira passagem, alertas de saturação e aprendizado pós-publicação.

## Importação e retenção

Em **Configurações**, somente administradores podem validar um export JSON completo do Trello. A prévia mostra cartões novos, alterados e já vinculados, o destino de cada lista no workflow padrão e a correspondência dos membros antes da aplicação. Por padrão, a importação cria apenas cartões ainda desconhecidos; a atualização de demandas existentes precisa ser habilitada explicitamente. O arquivo pode ter até 25 MB.

Cada lote guarda as alterações necessárias para reversão. Demandas criadas por um lote revertido são arquivadas, e demandas atualizadas voltam ao estado anterior. Além disso, um trigger do PostgreSQL salva a versão anterior de toda demanda alterada ou excluída.

A política inicial verifica a cada 60 dias as demandas concluídas sem alteração há pelo menos 60 dias. A ação apenas preenche `archived_at`: não remove demandas, tempos, comentários ou dados de performance. O administrador pode revisar a quantidade elegível, executar o arquivamento manualmente e restaurar itens depois.

## Implantação (Docker)

A plataforma roda com três serviços em `docker-compose.yml`: `app` (frontend + API na porta 8000),
`db` (PostgreSQL 17) e `backup` (dump diário do banco e dos anexos em `backups/`).
Não há dependência de Supabase nem de servidor de e-mail.

```bash
cp .env.example .env   # preencha DB_SENHA e os dois segredos (openssl rand -base64 48)
docker compose up -d --build
docker compose ps
curl http://localhost:8000/health
```

As migrations são aplicadas automaticamente antes de a API iniciar. Para atualizar:

```bash
git pull --ff-only
docker compose up -d --build app
```

Backup manual imediato: `docker compose exec backup /bin/sh /backup.sh agora`.
As instruções de restauração estão no cabeçalho de `scripts/backup.sh`.

A instalação atual usa HTTP na rede interna (`APP_ALLOW_INSECURE_HTTP=true`,
`APP_COOKIE_SECURE=false`). Ao colocar HTTPS na frente, inverta os dois valores.

### Desenvolvimento local

1. `docker compose up -d db` e um `.env` com `APP_DATABASE_URL` apontando para ele.
2. `python -m venv .venv` e `pip install -e "backend[dev]"`.
3. `alembic -c backend/alembic.ini upgrade head`.
4. `uvicorn app.main:app --app-dir backend --reload --port 8000` e `npm --prefix frontend run dev`.

## Acesso sem e-mail

- **Cadastro:** a pessoa cria a conta e fica pendente até um administrador liberar o acesso em **Usuários**.
- **Esqueci a senha:** um administrador usa **Redefinir senha** em **Usuários**. A plataforma gera uma
  senha temporária exibida uma única vez e encerra as sessões da pessoa; no login seguinte ela é obrigada
  a definir uma senha nova.
- **Troca de senha:** disponível em **Perfil**; encerra as demais sessões.
- Senhas usam bcrypt. Após 10 tentativas erradas, a conta fica bloqueada por 15 minutos.

## Primeiro administrador

Em uma instalação nova, configure `APP_BOOTSTRAP_ADMIN_EMAIL`. Ao se cadastrar com esse endereço, a plataforma o promove automaticamente como o primeiro administrador. A promoção só ocorre quando ainda não existe administrador ativo e fica registrada na auditoria.

Como alternativa operacional, após aplicar as migrations e verificar a identidade, execute `python -m app.scripts.bootstrap_admin --email administrador@empresa.com`. O comando se recusa a criar um segundo bootstrap se já houver administrador ativo.

Depois disso, o administrador libera novos cadastros pela área **Usuários**, escolhendo um dos perfis: administrador, coordenador, colaborador ou visualizador.

## Arquivos privados

Os anexos ficam no volume Docker `arquivos` (`/app/storage/demand-files`), no mesmo caminho
`organização/demanda/…` registrado em `app.demand_files`. A API confere a permissão sobre a demanda
antes de qualquer operação, e o download usa um link assinado que expira em
`APP_STORAGE_SIGNED_URL_TTL` segundos (120 por padrão).

O limite inicial é de 25 MB por arquivo (`APP_STORAGE_MAX_FILE_SIZE`). A remoção é lógica e interrompe
novos downloads. Os metadados, a soma SHA-256, os eventos da demanda e a auditoria permanecem no PostgreSQL.

## Migração do Supabase

Os dados vieram do export do projeto Supabase `fluxo-marketing-operacoes` (29/10/2026).
`scripts/supabase_export_to_sql.py` converte o `data.sql` do export: carrega o schema `app` e transforma
os usuários confirmados de `auth.users` em `app.auth_users`, preservando ids e hashes bcrypt (as senhas
continuam as mesmas). Os binários do bucket `demand-files` foram copiados para o volume `arquivos`.

## Formato da Daily

Use o schema `2.0` descrito em `../outputs/daily-import-v2.schema.json`. O arquivo `../outputs/daily-exemplo.json` pode ser usado como referência e para validação inicial do fluxo.

## Segurança operacional

- Segredos ficam apenas no `.env` (fora do Git, permissão restrita).
- Os anexos só saem da API por links assinados de curta duração.
- O PostgreSQL não publica porta no host; só a aplicação acessa o banco.
- Nunca usar dados reais nos ambientes de desenvolvimento e CI.
- O export original do Supabase fica em `migracao/` (fora do Git) e contém dados pessoais e hashes de senha.
