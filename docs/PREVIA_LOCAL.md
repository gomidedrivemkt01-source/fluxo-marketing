# Prévia local do Fluxo Marketing

Pasta: `C:\Users\Marketing 00\Documents\fluxo-local`.
Endereço da prévia: `http://127.0.0.1:18000`.

## Referência copiada em 04/11/2026

Código baseado na revisão do servidor `2462845745aa01ecfbc0e520f4db3102de2f03c0`, obtido pelo GitHub com as ferramentas da branch `codex/local-preview`. A aplicação em `http://192.168.0.160:8000` serve os arquivos de frontend correspondentes a essa base. A cópia contém os ajustes de responsáveis, equipe, etapas e exclusão segura de workflows da entrega anterior. A alteração preexistente em `Y:\scripts\backup.sh` foi preservada no servidor, que não recebeu gravações nesta preparação.

Em 04/11/2026, a pasta de trabalho passou a ser `C:\Users\Marketing 00\Documents\fluxo-local`. Os arquivos que faltavam foram completados a partir da branch `codex/local-preview` do GitHub, preservando os dois arquivos que já existiam na pasta. O banco ativo foi obtido por uma consulta somente de leitura no Supabase às 12:09:35 (America/Sao_Paulo) e restaurado no PostgreSQL local. Foram conferidas as contagens das tabelas e todas as referências de chaves estrangeiras: 1.117 demandas no total, 209 visíveis, 15 workflows, 5 usuários confirmados, 137 comentários e 3.767 atualizações. Os 20 objetos armazenados foram reaproveitados do cache local somente após validar tamanho e checksum contra os dados atuais da origem. As 1.708 referências de anexos incluem links externos do Trello, mantidos como links. A prévia não representa uma réplica exata do servidor: mudanças realizadas somente no servidor depois da migração não estão incluídas nessa cópia do Supabase.

O Docker Desktop deste computador falhou ao iniciar seu serviço de inferência. Por isso, esta prévia usa Python 3.12, PostgreSQL 17 portátil e o build React/Vite. O Dockerfile e o Compose do projeto continuam disponíveis para execução em uma instalação funcional do Docker. O teste do contêiner local continua pendente.

Validação realizada: build do frontend idêntico ao publicado, 13 testes do frontend, migrations até `0020_operational_management`, testes do backend incluindo integração em PostgreSQL 17, ensaio de dump/restauração com base sintética e respostas HTTP das rotas `/health`, `/team`, `/workflows` e `/demands`. A base sintética foi desativada ao final. A cópia real do Supabase está ativa, com autenticação normal e agendamento automático de retenção desativado somente na prévia.

## Isolamento

- Banco escuta apenas em `127.0.0.1:15432`; aplicação apenas em `127.0.0.1:18000`.
- Senhas e chaves novas são geradas em `.preview/settings.json`. Não copia o `.env` de produção.
- Banco, anexos, logs e snapshots ficam em `.preview/`, fora do Git e do contexto de build Docker.
- Cada restauração cria outro banco e outra pasta de anexos. A cópia anterior só deixa de ser a ativa depois de uma restauração validada. Não apaga bancos existentes.
- O agendamento automático de retenção fica desativado na prévia. O padrão de produção permanece ativado; as configurações de retenção copiadas não são alteradas no banco.
- Não há sincronização automática com produção. Alterações e uploads feitos na prévia ficam locais.
- O login usa as contas e as senhas presentes no backup, depois da restauração. Não há atalho para pular a autenticação.

## Preparar neste Windows

Requisitos: Python 3.12+, Node/npm e acesso à internet na primeira instalação. No PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Users\Marketing 00\Documents\fluxo-local'
& .\scripts\prepare-local-preview.ps1
```

Se Python não estiver no PATH, use `-Python 'C:\caminho\python.exe'`. O script prepara dependências, baixa o PostgreSQL oficial e aplica as migrations somente em um banco local de conferência da estrutura. Não cria contas ou cards de demonstração.

## Atualizar futuramente a cópia a partir do servidor

Para substituir a cópia atual do Supabase por uma réplica dos dados do servidor, usar o par de arquivos do mesmo backup:

- `fluxo_AAAA-MM-DD_HHMM.dump`: banco PostgreSQL completo, incluindo usuários, configurações, cards e históricos.
- `fluxo_arquivos_AAAA-MM-DD_HHMM.tar.gz`: volume de anexos completo.

O TI pode gerar o par no host que executa o Compose com `docker compose run --rm backup agora`, na pasta do projeto, e disponibilizar os dois arquivos em uma pasta com leitura permitida para este computador. Isso não requer habilitar SSH. Durante a cópia, evitar alterações nos cards/anexos para reduzir divergências entre os dois arquivos. Os backups agendados existentes também podem ser usados, declarando a data da cópia.

Não é necessário compartilhar a senha do banco nem o `.env` do servidor.

## Restaurar e abrir a prévia

Depois de os dois arquivos estarem acessíveis, ajuste os nomes nos comandos:

```powershell
& .\.venv\Scripts\python.exe scripts/local_preview.py restore `
    --database 'Y:\copia-preview\fluxo_2026-11-04_1200.dump' `
    --files 'Y:\copia-preview\fluxo_arquivos_2026-11-04_1200.tar.gz'
& .\.venv\Scripts\python.exe scripts/local_preview.py start
```

A restauração valida o formato do dump, os caminhos do arquivo de anexos, as tabelas obrigatórias, a revisão das migrations e a existência dos anexos ativos referenciados no banco. O manifesto em `.preview/snapshots/<copia>/manifest.json` registra hashes SHA-256, contagem de registros de cada tabela, quantidade/tamanho dos arquivos e horário da restauração. Ele confirma a integridade da cópia recebida; o estado real do servidor corresponde à data em que o backup foi gerado.

Abrir `http://127.0.0.1:18000` e entrar com a conta existente no backup. Nenhuma senha deve ser enviada no chat.

```powershell
# Consultar o estado (não mostra segredos).
& .\.venv\Scripts\python.exe scripts/local_preview.py status
# Parar aplicação e PostgreSQL locais, preservando os dados.
& .\.venv\Scripts\python.exe scripts/local_preview.py stop
```

## Ciclo das próximas entregas

1. Conferir em leitura se o servidor recebeu mudanças feitas em outro computador.
2. Alterar o código nesta pasta e validar com testes, build e navegação na prévia.
3. Informar o que mudou e o que falta; o usuário valida a prévia antes da publicação.
4. Fazer commit e enviar a branch `codex/` ao GitHub, somente com código e documentação.
5. Após a validação, publicar a versão aprovada na origem do servidor e recompilar/recriar o serviço pelo mecanismo disponível no servidor. Copiar o código em `Y:` sozinho não troca o conteúdo de uma imagem Docker já criada.
6. Validar saúde, versão e funções no endereço do servidor. Dados usados nos testes da prévia não são enviados à produção.

## Repetir a importação de um snapshot Supabase

O script `scripts/import_supabase_snapshot.py` recebe o CSV exportado pelo SQL Editor e cria um banco novo. Valida projeto, formato, compatibilidade de colunas, contagens, chaves estrangeiras e checksums dos anexos. Converte os usuários confirmados para o login local mantendo seus hashes bcrypt. Sessões antigas não são importadas. O CSV, os hashes de senha e os anexos são confidenciais: nunca devem entrar no Git.

O campo `compressed_snapshot` utiliza pgcrypto apenas como formato de transporte compactado; a frase fixa do formato não é uma proteção de sigilo. Tratar o CSV como dados pessoais legíveis e mantê-lo em local privado.

```powershell
& .\.venv\Scripts\python.exe scripts/import_supabase_snapshot.py --csv 'C:\copia-privada\supabase-snapshot.csv' --files-cache 'C:\copia-privada\storage\objects'
```
