# Arquitetura de carregamento e desempenho

## Navegação

As áreas do menu usam rotas reais (`/overview`, `/my-work`, `/demands`,
`/calendar`, `/reports` etc.). O backend mantém o fallback do documento-base para
permitir atualização direta em qualquer URL. Links antigos com `#` são convertidos
automaticamente para a rota equivalente.

O HTML permanece como um shell mínimo compartilhado. Em uma aplicação React,
duplicar o mesmo shell em vários arquivos HTML aumentaria manutenção e não reduziria
o processamento. A separação efetiva acontece nos dados e nos pacotes JavaScript:

- autenticação e área interna são pacotes distintos;
- calendário, relatórios, workflows e configurações são baixados apenas ao abrir;
- comentários, arquivos e apontamentos de tempo são baixados apenas ao abrir um card;
- passar o cursor ou o foco por um link inicia o pré-carregamento do respectivo pacote.

## Dados por página

`GET /api/v1/workspace/pages/{page}` retorna somente os conjuntos usados pela rota.
O início carrega perfil e demandas; relatórios não carregam a carteira; empresas não
carregam workflows; calendário recebe apenas demandas, pessoas e empresas. Dados já
visitados permanecem em memória durante a sessão e são invalidados após mutações.

A listagem de demandas resolve empresa, categoria, pessoas, etapa, workflow, versão e
capa em uma consulta SQL. Isso elimina as sete consultas adicionais que eram feitas
para montar cada resposta da carteira no PostgreSQL remoto.

## Renderização e ativos

- A galeria monta 48 cards por vez e amplia o lote conforme a rolagem.
- Cards fora da área visível usam `content-visibility`.
- Capas e avatares usam carregamento tardio e decodificação assíncrona.
- A fonte Inter carrega somente o arquivo latino necessário.
- React fica em um pacote estável com cache imutável entre versões da aplicação.

## Medição do build

Antes da mudança, a interface interna estava em um único arquivo JavaScript de
aproximadamente 461 KB (127 KB comprimidos). O pacote comum da área interna passou
para aproximadamente 144 KB (38 KB comprimidos), com os recursos especializados em
pacotes independentes de 7 KB a 21 KB. O CSS global permanece como próximo candidato
para divisão por área quando o volume de estilos crescer.
