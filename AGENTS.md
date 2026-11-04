# Ambiente de trabalho e publicação

Pasta ativa solicitada pelo usuário: `C:\Users\Marketing 00\Documents\fluxo-local`. Usar esta pasta nas próximas alterações. A pasta anterior em `Documents\Codex\fluxo-marketing-preview` foi substituída como ambiente de trabalho.

- Esta pasta é a prévia local independente do Fluxo Marketing. A origem de referência é `\\192.168.0.160\fluxo-marketing` (`Y:`), aplicação `http://192.168.0.160:8000`.
- Desenvolver e validar aqui, em `http://127.0.0.1:18000`, antes de publicar no servidor. Não escrever em `Y:` nem ativar versões no servidor durante o desenvolvimento da prévia. A publicação ocorre após a validação da prévia pelo usuário.
- Antes de uma nova entrega, conferir a versão atual do servidor em modo de leitura para preservar alterações feitas em outros computadores.
- Manter banco, anexos, segredos, logs e backups locais dentro de `.preview/`, ignorada pelo Git. Nunca usar as credenciais, o banco ou os volumes de produção para executar testes.
- A base ativa foi copiada do Supabase em 04/11/2026 e adaptada ao código atual. Não apresentá-la como réplica exata do servidor: mudanças feitas apenas no servidor após a migração podem estar ausentes. Manter a origem e a data do snapshot registradas no manifesto local.
- Registrar o código de cada entrega em uma branch `codex/` e enviar o versionamento ao GitHub. Não enviar backups, senhas ou dados pessoais ao GitHub.
- Informar o que foi validado e o que falta antes da próxima etapa.
