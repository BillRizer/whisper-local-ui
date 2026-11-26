# PRD — Whisper Local

Estado: reconstruído a partir do código e README existentes em 2026-11-25; não representa aprovação histórica. Responsável e métricas de produto ainda não definidos.

## Problema e público

Pessoas e agentes locais precisam converter fala de áudio ou vídeo em texto sem enviar o conteúdo a uma API de transcrição. O usuário opera a interface web; um cliente de automação pode usar MCP ou HTTP no mesmo computador.

## Objetivo e escopo atual

- Transcrever no idioma original ou traduzir fala para inglês, usando faster-whisper localmente.
- Aceitar lote de até 20 uploads de até 1 GB cada, gravação no navegador e caminho local via MCP.
- Acompanhar uma fila sequencial e consultar resultados, incluindo após reinício quando concluídos.
- Exportar TXT, SRT, VTT e JSON; controlar descarregamento do modelo.

Fora do escopo atual: colaboração multiusuário, autenticação, tradução para destinos arbitrários e garantia de precisão de reconhecimento. O primeiro uso pode baixar pesos de modelo; processamento local não significa ausência total de tráfego de rede.

## Critérios de aceite

1. Um upload válido retorna trabalho enfileirado; estado progride até conclusão ou erro consultável. Entradas inválidas são rejeitadas.
2. Resultados concluídos podem ser recuperados após reinício e exportados nos formatos suportados; o usuário pode remover registros.
3. Uploads temporários são removidos após sucesso, exclusão do trabalho ou reinício; falhas podem ser reenfileiradas enquanto o arquivo estiver disponível. Arquivos originais indicados por MCP são preservados.
4. O serviço inicia em loopback por padrão e permite configurar explicitamente o endereço de escuta; MCP compartilha fila e histórico com a interface.
5. A interface distingue transcrição de tradução para inglês e mostra progresso e falhas.

Os testes automatizados cobrem parte desses critérios com backend simulado; gravação, precisão real, GPU e experiência visual exigem validação manual. Consulte `testes.md`.

## Questões abertas

Definir público prioritário, metas mensuráveis de qualidade/tempo, política de retenção, plataformas suportadas e critérios de acessibilidade com o responsável pelo produto. Não há dados de usuários ou métricas de sucesso disponíveis neste repositório.
