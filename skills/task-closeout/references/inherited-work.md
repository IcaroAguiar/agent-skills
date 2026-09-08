# Pendências herdadas e recuperação

Antes de mover ou restaurar trabalho anterior, apresente o recorte e um plano reversível. A autorização existente vale; não peça novamente por inventário ou ações reversíveis já autorizadas. Origem incerta continua sendo pendência, não lixo.

1. Distinga o que já está integrado do que precisa de revisão. Conteúdo igual à base é um sinal; confira também index, modo do arquivo, renames e contexto. Nunca confunda o diff inteiro de um arquivo com a contribuição da tarefa.
2. Quando a preservação exigir arquivo externo, escolha **uma** forma de recuperação, em **um** local identificado. Inclua base/HEAD, caminhos, staged/unstaged, untracked necessários e hashes. Preserve symlinks sem seguir alvos externos. Verifique o conteúdo e descreva como recuperá-lo antes de remover a origem.
3. Restaure somente os caminhos inventariados, conferindo que não mudaram desde a captura. Preserve `.env`, credenciais, certificados, bancos, volumes e registros de negócio fora de qualquer limpeza genérica. Alterá-los exige escopo e autorização próprios.
4. Dê destino explícito ao restante: entrega integrada, trabalho pendente identificado ou recurso ainda em uso. Um backup não transforma trabalho pendente em tarefa concluída. Não replique o arquivo de recuperação em várias pastas e não o abandone sem indicar conteúdo e próximo passo.

Se uma proteção automática bloquear a ação, informe ação e motivo. Corrija o alvo ou a condição verificada; não disfarce comandos nem desative a proteção. Se não houver um caminho seguro, mantenha o trabalho preservado e reporte o bloqueio.
