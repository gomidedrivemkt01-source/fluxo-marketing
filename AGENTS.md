# Ambiente de trabalho e publicação

- Esta pasta é a prévia local independente do Fluxo Marketing. A origem de referência é `\\192.168.0.160\fluxo-marketing` (`Y:`), aplicação `http://192.168.0.160:8000`.
- Desenvolver e validar aqui, em `http://127.0.0.1:18000`, antes de publicar no servidor. Não escrever em `Y:` nem ativar versões no servidor durante o desenvolvimento da prévia. A publicação ocorre após a validação da prévia pelo usuário.
- Antes de uma nova entrega, conferir a versão atual do servidor em modo de leitura para preservar alterações feitas em outros computadores.
- Manter banco, anexos, segredos, logs e backups locais dentro de `.preview/`, ignorada pelo Git. Nunca usar as credenciais, o banco ou os volumes de produção para executar testes.
- Não apresentar uma base vazia ou dados de demonstração como réplica dos dados atuais. Sem um backup atual do banco e dos anexos, declarar a cópia dos dados como pendente.
- Registrar o código de cada entrega em uma branch `codex/` e enviar o versionamento ao GitHub. Não enviar backups, senhas ou dados pessoais ao GitHub.
- Informar o que foi validado e o que falta antes da próxima etapa.
