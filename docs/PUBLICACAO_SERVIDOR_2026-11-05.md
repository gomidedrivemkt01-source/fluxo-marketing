# Ativação da versão validada no servidor

A versão da prévia inclui gestão compartilhada de funções/etapas, remoção da busca na Equipe, filtros responsivos de Relatórios e filtros compactos do Calendário com categoria.

Os arquivos de código são atualizados na origem `\\192.168.0.160\fluxo-marketing` (`Y:`). O `.env`, o Compose, o script de backup customizado pelo TI e os dados de produção são preservados. Nenhum banco ou anexo da prévia é enviado ao servidor.

## Ativar no host que executa o Docker

A aplicação usa código compilado dentro da imagem, sem montagem do código-fonte. Atualizar os arquivos compartilhados prepara a versão, mas não altera o container já em execução. Não há contexto Docker remoto configurado no computador de desenvolvimento.

No terminal do próprio servidor, entrar na pasta que contém `docker-compose.yml` e executar:

```sh
sh scripts/atualizar-servidor.sh
```

O script valida a configuração sem imprimir segredos, preserva a imagem anterior, cria e confere backups do banco/anexos de produção em `backups/atualizacoes/<data_hora>/`, recompila e recria somente `app`. Os serviços `db` e `backup` e os volumes existentes permanecem em uso. O script não limpa backups anteriores.

O inicializador aplica a migration aditiva `0021_stage_function_defaults` antes de abrir a aplicação. Ela acrescenta uma coluna JSONB nullable; não reescreve demandas nem históricos. A aplicação é considerada ativa somente depois da verificação de saúde do Compose e de `/health`.

Após a ativação, recarregar o navegador em `http://192.168.0.160:8000/calendar`. Conferir o botão de funil e o campo Categoria, além de Workflows → Funções e etapas.

## Se a ativação falhar

Consultar `docker compose logs --tail 100 app` no servidor. O script interrompe a sequência se qualquer backup, build ou verificação falhar. Uma falha durante build mantém o serviço anterior; uma falha após recriar `app` exige conferir os logs e, se necessário, reativar a imagem preservada.

O nome da imagem anterior fica em `backups/atualizacoes/<data_hora>/imagem-anterior.txt`. É possível retaguar essa imagem como `fluxo-marketing:latest` e recriar somente `app` com `--no-build`. A coluna adicionada é compatível com o código anterior; não é necessário desfazer a migration para reativar a imagem antiga. Não restaurar o banco automaticamente, pois isso perderia alterações realizadas depois do backup.
