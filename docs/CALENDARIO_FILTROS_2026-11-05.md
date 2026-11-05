# Filtros compactos do calendário

Entrega para a prévia local em `http://127.0.0.1:18000/calendar`.

- O botão de funil **Filtros** concentra busca, categoria, responsável, empresa, situação e prioridade. O contador indica quantos filtros estão ativos mesmo com o menu fechado.
- Categoria inclui todas as categorias cadastradas, categorias desativadas ainda usadas pelos cards e **Sem categoria**.
- Mês e Agenda por dia compartilham o mesmo filtro combinado; alternar a visualização ou navegar pelos meses mantém as escolhas enquanto o calendário estiver aberto.
- Os resultados e contadores mudam imediatamente. **Ver resultados**, Escape, o botão de fechar e clique fora recolhem o menu. **Limpar filtros** restaura todos os campos.
- O painel usa as cores do tema pessoal, duas colunas flexíveis e rolagem interna. Em celulares, aparece como um painel junto à base da tela para manter os campos e ações acessíveis.
- A rota de carregamento individual do calendário inclui o catálogo de categorias, sem carregar workflows ou etapas extras. O filtro atua sobre a carteira já autorizada pela API.

Não há migration, alteração de demandas ou mudança de dados nesta entrega. Validação técnica: build e 13 testes do frontend passaram; 7 testes do carregamento da carteira passaram, incluindo o acesso direto ao calendário com categorias e sem os catálogos de workflows. Ruff passou nos módulos de backend alterados.

A conferência visual na prévia e o versionamento no GitHub são realizados antes da entrega. A publicação no servidor continua dependendo da validação da prévia pelo usuário.
