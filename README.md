# Fluxo Marketing

Fundação da plataforma interna de gestão e inteligência operacional do Marketing.

O MVP entrega autenticação por e-mail e senha com código, recuperação de senha, aprovação administrativa, perfis de acesso, criação e edição manual de demandas, empresas, categorias, perfil com foto, auditoria e importação assistida de Dailys.

A criação manual é a entrada principal da operação. A interface organiza o trabalho em Início, Meu trabalho, Demandas, Calendário, Empresas, Equipe, Relatórios, Inteligência e Administração. Cada demanda pode receber empresa, categoria, prioridade, prazo, situação e descrição.

O upload de uma Daily é um recurso complementar na área de Inteligência e nunca altera cards automaticamente. A aplicação valida o JSON, abre cada item para revisão e exige uma escolha explícita: associar a um card existente, criar um card ou ignorar. As atualizações são aplicadas em uma única operação somente depois que todos os itens forem revisados. Revisões interrompidas ficam disponíveis para continuação.

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

## Formato da Daily

Use o schema `2.0` descrito em `../outputs/daily-import-v2.schema.json`. O arquivo `../outputs/daily-exemplo.json` pode ser usado como referência e para validação inicial do fluxo.

## Segurança operacional

- Segredos ficam apenas nas variáveis do serviço.
- O schema operacional não deve ser exposto pela Data API.
- A conexão de runtime não deve ser dona das tabelas nem possuir `BYPASSRLS`.
- Nunca usar dados reais nos ambientes de desenvolvimento e CI.
- Backups de PostgreSQL e Storage são processos separados.
