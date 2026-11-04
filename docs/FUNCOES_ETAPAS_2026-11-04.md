# Funções compartilhadas entre etapas

Entrega preparada para a prévia em `C:\Users\Marketing 00\Documents\fluxo-local`, sem publicação no servidor.

## Navegação

- **Workflows → Funções e etapas** abre o catálogo de funções e os vínculos compartilhados.
- **Equipe → Gerenciar funções** abre a mesma interface.
- Cada função permite cadastrar/editar nome e descrição, escolher principal/substituto e excluir.
- Na pessoa da Equipe, as atribuições continuam usando as mesmas funções do catálogo.
- A busca de pessoa/e-mail da página Equipe foi removida.

## Vínculo de etapas

Etapas ativas de workflows ativos são agrupadas pelo nome, ignorando caixa, acentos e espaçamento/pontuação. “Revisão (Criação)” e “Revisão (Técnica)” continuam separadas. Etapas com nomes diferentes podem ser vinculadas à mesma função.

Exemplo: selecionar Planejamento de Demandas para o grupo Briefing, ou Copywriter para o grupo Copy/Redação correspondente. O sistema mostra os workflows envolvidos e o impacto antes de confirmar. A confirmação substitui os padrões específicos dessas etapas pelo principal e substituto da função; exceções atribuídas diretamente aos cards permanecem preservadas.

O vínculo vale para os modelos, para as etapas futuras dos cards e, se selecionado, para as etapas atuais. As versões históricas de workflow e as etapas concluídas não são reescritas. Novas etapas de mesmo nome herdam uma função quando o grupo tem definição única; se houver definições divergentes, a pessoa precisa escolher explicitamente uma função.

## Exclusão de função

A revisão mostra etapas e demandas afetadas. A exclusão remove os vínculos dos modelos e desativa as atribuições da função. Cada etapa volta a usar seu principal/substituto próprio; sem padrão, fica sem responsável. Pessoas atribuídas especificamente aos cards não são apagadas nem substituídas.

A identidade antiga fica inativa para preservar referências históricas. Nome/código são liberados para um novo cadastro com identidade diferente; assim uma nova função não reativa vínculos históricos. A auditoria registra o nome/código original e o impacto. Timers em execução que precisariam trocar de responsável impedem a operação antes de qualquer alteração.

## Persistência e validação

A migration aditiva `0021_stage_function_defaults` acrescenta uma coluna JSONB nullable às instâncias de etapa. Ela guarda apenas os novos padrões de atribuição operacional, preservando o conteúdo das versões imutáveis e evitando que o próximo avanço restaure o vínculo antigo.

As operações exigem `catalog:write`, CSRF, escopo da organização e revisão atual dos registros. Mudanças concorrentes no grupo exigem recarregar antes de aplicar. Testes PostgreSQL usam exclusivamente `fm_test_management` em loopback, com dados sintéticos e rollback.

Os filtros de Relatórios passaram a usar colunas flexíveis, limites de largura nos campos e empilhamento em telas pequenas, inclusive no intervalo personalizado. A privacidade dos relatórios não foi modificada.
