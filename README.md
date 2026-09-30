# Fluxo Marketing

Fundação da plataforma interna de gestão e inteligência operacional do Marketing.

O MVP entrega autenticação por e-mail e senha com código, recuperação de senha, aprovação administrativa, perfis de acesso, criação e edição manual de demandas, responsáveis, workflows reutilizáveis, visões pessoais em Kanban e lista, empresas, categorias, briefings configuráveis, checklists por etapa e por card, comentários, histórico, timer, arquivos privados, perfil com foto, auditoria e importação assistida de Dailys.

A criação manual é a entrada principal da operação. **Início** funciona como agenda pessoal e separa as entregas em atrasadas, hoje, amanhã e datas futuras. **Meu trabalho** permite criar, ordenar e colorir colunas pessoais em Kanban ou lista sem alterar o workflow compartilhado. Ao filtrar um responsável, a equipe vê a organização escolhida por essa pessoa; ao combinar responsáveis, a plataforma usa uma lista única.

Administradores e coordenadores mantêm uma biblioteca de workflows na área **Workflows**. Cada modelo possui suas próprias etapas, checklists, responsáveis padrão e durações esperadas. Uma categoria pode apontar para seu workflow padrão, e um card pode substituir esse modelo quando precisar de um fluxo específico. A migração inicial preserva o fluxo existente como **Fluxo padrão**.

Cada demanda guarda a versão imutável do workflow usada no momento da criação ou da troca explícita de fluxo. Alterações posteriores no modelo passam a valer para novos cards sem modificar retroativamente as demandas em andamento. A aba **Workflow** combina o histórico real com a agenda de cada etapa, permite ajustar prazo e previsão e destaca etapas vencidas ou em risco. As ações **Retornar**, **Pular** e **Avançar** registram o handoff; a saída é bloqueada enquanto houver timer aberto e o avanço também exige os itens obrigatórios do checklist. Uma versão compacta dessa timeline aparece na visão geral do card.

Na área **Categorias**, a administração combina workflow e modelo de briefing. Dentro do card, a visão geral reúne dados essenciais, timer, checklist rápido e uma lateral que alterna entre comentários e histórico. As abas avançadas preservam o briefing completo, workflow, checklist, arquivos, atividade e tempo. O timer pode ser iniciado, pausado, retomado e concluído; a aba de tempo mantém o ajuste manual e o histórico da equipe.

O upload de uma Daily é um recurso complementar na área de Inteligência e nunca altera cards automaticamente. A aplicação valida o JSON, abre cada item para revisão e exige uma escolha explícita: associar a um card existente, criar um card ou ignorar. As atualizações são aplicadas em uma única operação somente depois que todos os itens forem revisados. Revisões interrompidas ficam disponíveis para continuação.

## Plano de execução ativo

- **Marco 1 — Fundação e acesso:** autenticação, aprovação, perfis, cadastros, auditoria e infraestrutura online concluídos.
- **Marco 2 — Card operacional:** criação manual, briefing, checklist, comentários, histórico, arquivos privados e timer concluídos.
- **Marco 3 — Fluxo e foco pessoal:** agenda Todoist, Kanban pessoal, biblioteca de workflows, versões imutáveis, agenda por etapa, handoffs validados e alertas de risco concluídos nesta base.
- **Próximo marco — Relatórios operacionais:** indicadores de prazo, volume, tempo investido e gargalos por empresa, categoria, responsável e etapa, usando o histórico operacional já persistido.

## Execução local

Pré-requisitos: Node.js 24+, Python 3.12+ e Docker Desktop com Compose.

1. Copie `.env.example` para `.env` e preencha as configurações do projeto de homologação.
2. Inicie o PostgreSQL: `docker compose -f infra/compose.yaml up -d db`.
3. Crie o ambiente Python e instale o backend: `python -m venv .venv`, `.venv\Scripts\python -m pip install -e backend[dev]`.
4. Aplique as migrations: `.venv\Scripts\alembic -c backend/alembic.ini upgrade head`.
5. Instale o frontend: `npm --prefix frontend install`.
6. Inicie a API: `.venv\Scripts\uvicorn app.main:app --app-dir backend --reload --port 8000`.
7. Inicie a interface: `npm --prefix frontend run dev`.

Abra `http://localhost:5173`. O Vite encaminha `/api` para a API local.

## Configuração do Supabase Auth

- Authentication > Providers > Email: habilitar e-mail/senha e confirmação de e-mail.
- Desabilitar Google, outros provedores sociais e sign-in anônimo.
- Authentication > Email > SMTP: usar o SMTP autorizado.
- Templates de confirmação e recuperação: usar `{{ .Token }}` para mostrar o código numérico.
- Site URL e Redirect URLs: cadastrar somente as origens de homologação e produção.

O backend usa apenas a URL do projeto e a chave publicável para os fluxos do usuário. Credenciais administrativas não são expostas ao frontend.

## Primeiro administrador

Configure `APP_BOOTSTRAP_ADMIN_EMAIL` no ambiente de produção. Depois de cadastrar esse endereço e confirmar o código recebido, a plataforma o promove automaticamente como o primeiro administrador. A promoção só ocorre quando ainda não existe administrador ativo e fica registrada na auditoria.

Como alternativa operacional, após aplicar as migrations e verificar a identidade, execute `python -m app.scripts.bootstrap_admin --email administrador@empresa.com`. O comando se recusa a criar um segundo bootstrap se já houver administrador ativo.

Depois disso, o administrador libera novos cadastros pela área **Usuários**, escolhendo um dos perfis: administrador, coordenador, colaborador ou visualizador.

## Arquivos privados

A migration cria o bucket privado `demand-files` no Supabase Storage e aplica políticas que verificam o usuário, a organização e a demanda. O backend envia e assina arquivos com o token do próprio usuário; nenhuma chave administrativa do Storage é necessária.

O limite inicial é de 25 MB por arquivo. São aceitos PDF, imagens, documentos do Microsoft 365, texto, CSV, áudio e vídeo nos formatos configurados na migration. A remoção é lógica e interrompe novos downloads; links assinados expiram em 120 segundos. Os metadados, a soma SHA-256, os eventos da demanda e a auditoria permanecem no PostgreSQL.

Os valores podem ser ajustados por `APP_STORAGE_BUCKET`, `APP_STORAGE_MAX_FILE_SIZE` e `APP_STORAGE_SIGNED_URL_TTL`. O limite configurado na aplicação deve permanecer alinhado ao limite do bucket.

## Formato da Daily

Use o schema `2.0` descrito em `../outputs/daily-import-v2.schema.json`. O arquivo `../outputs/daily-exemplo.json` pode ser usado como referência e para validação inicial do fluxo.

## Segurança operacional

- Segredos ficam apenas nas variáveis do serviço.
- O bucket de demandas permanece privado e libera downloads somente por URLs assinadas de curta duração.
- O schema operacional não deve ser exposto pela Data API.
- A conexão de runtime não deve ser dona das tabelas nem possuir `BYPASSRLS`.
- Nunca usar dados reais nos ambientes de desenvolvimento e CI.
- Backups de PostgreSQL e Storage são processos separados.
