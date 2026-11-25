# Navegação superior e visão geral

A navegação lateral foi substituída por uma cápsula flutuante no topo. A marca permanece à esquerda, enquanto os avisos da carteira e o avatar ficam isolados à direita. Os grupos Trabalho, Equipe, Análise e Gestão reúnem as rotas existentes. Gestão continua restrita aos perfis autorizados; configurações administrativas mantêm a restrição original a administradores.

O menu do avatar abre o perfil, onde permanecem os dados pessoais e a edição da interface, e oferece a saída da conta. O sino apresenta atrasos e aprovações da própria carteira, carregados ao abrir o painel; ele não representa uma nova caixa de mensagens nem notificações de terceiros.

## Visão geral

- Grade de 12 colunas no desktop: quatro indicadores, próximas entregas em oito colunas, aprovações em quatro e fila de produção em largura total.
- Administradores e coordenadores alternam entre equipe e carteira própria. Colaboradores visualizam a própria carteira nessa tela. As permissões dos relatórios permanecem independentes e inalteradas.
- Atraso considera o instante do prazo, incluindo horários vencidos no dia atual. A semana respeita o fuso do perfil e vai de segunda a domingo. O período selecionado controla o indicador de entregas e o painel de próximas entregas; atrasos, aprovações e agendamentos representam a carteira ativa atual.
- Aprovações são reconhecidas pela situação ou pelo nome da etapa atual, sem duplicar o card. Concluídas continuam fora da carteira ativa.
- Os indicadores direcionam a fila para sua seleção. Marca, responsável e prioridade delimitam a visão; busca e situação refinam a fila. Ao abrir e voltar de um card, as seleções permanecem.
- Os timers permanecem disponíveis nas linhas de produção e no componente flutuante existente.

## Composição e compatibilidade

As cores derivam das paletas individuais já salvas. O campo persistido `sidebar` passa a colorir a cápsula de navegação e aparece como Navegação no editor; nenhum perfil de cores é migrado ou apagado. A interface conserva Inter, usa margens de 24–32 px no desktop e 16 px em telas pequenas, bordas sutis e sombras nos elementos sobrepostos.

O calendário aproveita a largura liberada pelo menu lateral. Galeria e Kanban preservam sua rolagem interna; a barra de etapas dos cards se estende à largura do viewport. Em telas pequenas, a navegação ocupa uma segunda linha compacta, os indicadores usam duas colunas e os painéis são empilhados.

## Verificação e entrega

- 22 testes de frontend e compilação TypeScript/Vite.
- Chrome com dados sintéticos em 1920, 1440, 1024, 768, 390 e 320 px.
- Verificação de menus por teclado, calendário mensal e agenda, produção, perfil, paletas clara/escura, avisos operacionais e posicionamento da barra de etapas.
- Regressão de filtros persistentes, consulta lateral, retorno do card, conclusão, arquivo e restauração.

Esta entrega altera somente o frontend. Não há migração de banco nem modificação de workflows, funções ou históricos. A cópia principal é `C:\Users\Marketing 00\Documents\fluxo-local`, com preview em `http://127.0.0.1:18000/overview`. A publicação no servidor ocorre após a validação visual do usuário, conforme `AGENTS.md`.
