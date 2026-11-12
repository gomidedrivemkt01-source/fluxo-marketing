# Workflows simplificados

A gestão de etapas exibe função, principal e substituto. O checklist automático saiu do menu de cada etapa. Os critérios textuais do manual continuam como orientação; sincronizar os rascunhos não gera novos checklists. Os checklists manuais dos cards continuam disponíveis.

A configuração local organiza as responsabilidades em Aprovação, Briefing, CopyWriter, Designer, Edição de Vídeo, Social Media e Áudio Visual (Gravação). São 100 etapas vinculadas a essas funções. Outras 22 mantêm suas atribuições técnicas ou específicas do card. A ordem, os nomes e os prazos das etapas não foram alterados.

## Aplicação dos dados

`backend/app/workflow_simplification.py` aplica uma configuração de forma transacional, reaproveitando a gestão de responsabilidades. Propaga os novos padrões às etapas atuais e futuras de cards abertos, preserva atribuições individuais diferentes do padrão anterior e não redistribui cards concluídos. Timers em execução que seriam afetados impedem a aplicação.

Os itens automáticos são desativados, sem apagar os registros de preenchimento. Versões antigas dos workflows permanecem imutáveis; novas versões refletem a configuração atual. A auditoria registra os vínculos e os IDs desativados. Reaplicar a mesma configuração não cria novas funções, versões, revisões ou eventos sem necessidade.

A configuração JSON contém dados pessoais e deve ficar fora do Git, no diretório privado do ambiente. Estrutura:

```json
{
  "functions": [
    {
      "code": "BRIEFING",
      "name": "Briefing",
      "primaryName": "Nome completo do principal",
      "fallbackName": "Nome completo do substituto"
    }
  ],
  "stages": [
    {
      "workflowCode": "CODIGO_DO_WORKFLOW",
      "stageCode": "BRIEFING",
      "functionCode": "BRIEFING"
    }
  ]
}
```

O nome deve identificar exatamente um integrante ativo. Os códigos das etapas precisam existir na organização; nenhum card, pessoa ou workflow é excluído. Todos os checklists automáticos ativos da organização são desativados, inclusive os de etapas inativas.

Com as variáveis de ambiente do banco correto carregadas, executar a partir de `backend/`:

```sh
python -m scripts.simplify_workflows --organization marketing --actor "Administrador ativo" --config /caminho/privado/configuration.json
```

Sem `--apply`, a simulação desfaz suas escritas temporárias. Conferir o impacto e criar um backup verificado antes de executar novamente com `--apply`. A transação é confirmada somente ao concluir toda a operação. Para reverter integralmente, restaurar o backup em uma cópia isolada e validar antes de substituir qualquer ambiente em uso.

## Validação e publicação

Testes de integração verificam preservação de históricos/checklists manuais, atribuições individuais, cards concluídos, versões imutáveis, repetição sem duplicação e ausência de geração automática no blueprint. A entrega é ativada primeiro na prévia local. A publicação no servidor exige validação dessa prévia e aplicação da configuração no banco do servidor; copiar somente o código não altera seus responsáveis nem seus checklists existentes.

Validação desta entrega: 212 testes de backend, 15 testes de frontend, build, Ruff e checagem de tipos dos módulos novos. Conferência visual com conta sintética em 1440px e 390px: responsáveis visíveis, menu sem checklist, acesso à gestão de funções, ausência de transbordamento horizontal e de erros de JavaScript. A aplicação local preservou as contagens das 44 tabelas existentes e as 17 versões históricas. Os 309 itens automáticos foram desativados; os 100 registros de preenchimento e 526 itens manuais foram preservados.

## Publicação com Docker

O comando também está empacotado na imagem: `python -m app.workflow_simplification_cli`. Ele aceita `--config -` para ler JSON pela entrada padrão, sem copiar dados pessoais para a imagem ou precisar montar pastas adicionais.

Para uma publicação com atualização de workflows, definir `FM_WORKFLOW_CONFIG` com o caminho do JSON no host e `FM_WORKFLOW_ACTOR` com o nome exato do administrador. Executar `sh scripts/atualizar-servidor.sh` no host Docker. O script preserva a imagem anterior, confere backups do banco/anexos, compila a imagem e executa a simulação e a aplicação no banco do servidor antes de ativar o novo container. Uma falha em qualquer dessas duas operações interrompe a ativação. Os resultados privados ficam em `backups/atualizacoes/<data_hora>/workflows-*.json`.

O diretório `.deployments/` é ignorado pelo Git e pelo contexto Docker para guardar a configuração específica do servidor. Nunca enviar o banco ou os anexos da prévia para esse processo. Copiar os arquivos em Y: prepara a publicação; o comando deve ser executado no host que controla o Docker.

Se uma função já existir com o mesmo nome e outro código gerado pela interface, sua identidade e código são reaproveitados. Se o código solicitado e o nome apontarem para funções diferentes, a publicação é interrompida para resolver a ambiguidade. Etapas ou integrantes ausentes também impedem a aplicação, sem alterações parciais. Validação do pacote de publicação: 215 testes de backend, incluindo entrada de configuração por arquivo/stdin e reaproveitamento de funções existentes.
