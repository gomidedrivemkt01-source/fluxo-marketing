# Versão visível e publicação — 26/11/2026

Esta entrega publica a correção das colunas pessoais em HTTP e passa a identificar a interface como **6.1.2**.

O número fica centralizado acima da cápsula de navegação, em 10 px, peso 400, sem fundo, borda ou preenchimento. O posicionamento absoluto mantém o número fora do fluxo de espaçamento; não desloca o menu ou a área de trabalho. A cor acompanha a paleta do usuário.

A fonte única do número é `frontend/package.json`, importada pelo cabeçalho. O lockfile registra a mesma versão. Em cada publicação futura, atualizar a versão desse pacote e do lockfile, por exemplo com `npm version patch --no-git-tag-version` dentro de `frontend`, antes de compilar e registrar o commit. O número é compilado junto do frontend: somente uma imagem recompilada passa a mostrar a nova versão; copiar código para o compartilhamento não modifica o container existente.

## Pacote desta entrega

- Correção do gerador de identificadores para HTTP na rede, com persistência e recuperação de erros no editor de colunas.
- Versão discreta no cabeçalho de todos os módulos autenticados.
- Nenhuma nova migração de banco. As tabelas, vínculos, preferências existentes e históricos permanecem em uso.
- 26 testes de interface e compilação TypeScript/Vite. Posição, fonte regular, navegação e ausência de deslocamento verificados em 1920, 1440, 1024, 768, 390 e 320 px, em ambiente sintético isolado.
- Por solicitação do usuário, o pequeno ajuste visual segue diretamente para o pacote do servidor; a prévia principal não é recompilada nesta etapa.

## Ativação pelo TI

Após copiar e verificar o pacote na origem do servidor, o comando da entrega atual fica registrado em `.deployments/release.json`:

```sh
sh .deployments/atual/publicar.sh
```

Executar no host Docker, dentro da pasta que contém `docker-compose.yml`. O comando utiliza o procedimento existente para preservar a imagem anterior, conferir backups do banco e dos anexos, recompilar e recriar somente `app`. Não reaplica configurações antigas de pessoas e workflows.

Depois, o verificador confere a revisão do banco já existente, os arquivos efetivamente usados no container, os componentes compilados e a versão **6.1.2**. O recibo fica em `.deployments/atual/activation.json`. Recarregar a plataforma e conferir o número acima do menu. A cópia dos arquivos e a ativação da imagem são etapas distintas.
