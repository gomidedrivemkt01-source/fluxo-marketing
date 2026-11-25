# Correção de criação de colunas pessoais — 25/11/2026

## Causa reproduzida

O botão **Meu trabalho → Minhas colunas → Adicionar coluna** chamava `crypto.randomUUID()` dentro do atualizador de estado React. No endereço HTTP do servidor (`http://192.168.0.160:8000`), essa API não está disponível porque a origem não é um contexto seguro. O localhost é considerado seguro pelo navegador, o que mascarava o problema na prévia.

A conferência do navegador mostrou `randomUUID: undefined` na rede e `randomUUID: function` no localhost; `getRandomValues` está disponível em ambos. Ao reproduzir a indisponibilidade em uma conta sintética, o clique lançou `crypto.randomUUID is not a function` e desmontou a interface.

## Correção

- Um gerador compartilhado usa a API nativa quando disponível e gera UUID v4 com `crypto.getRandomValues` quando necessário. Não usa `Math.random` nem acrescenta dependências.
- A geração ocorre antes de atualizar o estado. Uma falha excepcional passa a aparecer no editor, em vez de derrubar o React.
- Colunas, visões salvas e novos perfis de cores usam o mesmo gerador compatível com HTTP. Os identificadores já existentes permanecem iguais.
- O editor direciona o foco para o nome da nova coluna e informa o limite existente de 12 colunas, correspondente à API.
- O botão de salvar aguarda a confirmação da API. Falhas de gravação mantêm o editor aberto, preservam o rascunho, exibem a mensagem e permitem tentar novamente. Os controles ficam desabilitados durante a gravação.
- Os campos têm nomes e rótulos próprios, permitindo que a validação destaque o nome da coluna que precisa ser preenchido.

As mudanças afetam apenas o frontend. Não há migração, mudança no limite do banco, recriação de colunas existentes ou alteração de etapas e responsáveis dos workflows.

## Verificação

- 26 testes de frontend e build TypeScript/Vite.
- Reprodução anterior à correção com a API indisponível.
- Chrome em origem HTTP sintética efetivamente não segura (`isSecureContext=false`, `randomUUID=undefined`), encaminhada exclusivamente ao ambiente descartável local.
- Criação, foco, nome, cor, persistência e recarregamento; falha de gravação simulada e nova tentativa; cancelamento; campo obrigatório identificado; limite de 12; salvamento em 390 px.
- Criação de visão salva e perfil de cores na mesma origem HTTP, pois utilizavam a mesma chamada incompatível.

Somente a conta e o banco sintéticos receberam gravações de teste, com restauração das preferências ao final. A prévia principal é atualizada após a verificação; a publicação no servidor depende da validação dessa correção.
