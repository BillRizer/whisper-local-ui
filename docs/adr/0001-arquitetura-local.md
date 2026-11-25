# ADR 0001 — Processamento local e fila compartilhada

Estado: reconstruído em 2026-11-25 a partir da implementação existente; não há registro de quando ou por quem a decisão original foi tomada.

## Contexto

A interface e o MCP precisam executar transcrição no computador e compartilhar estado, sem depender de uma API externa de transcrição.

## Decisão observada

FastAPI hospeda UI, API e MCP no mesmo processo; um `JobManager` serializa trabalhos em um worker e reutiliza um modelo faster-whisper. Uploads são temporários; resultados concluídos são persistidos localmente. Pesos podem ser baixados na primeira utilização.

## Consequências e alternativas

A solução simplifica a implantação e reduz contenção pelo modelo, mas limita throughput, perde a fila em reinícios e requer cuidado com dados locais. Uma fila persistente com processos separados facilitaria recuperação e escala, ao custo de infraestrutura e coordenação; não há evidência de que essa alternativa tenha sido formalmente avaliada originalmente. Mudanças nessa decisão exigem novo ADR e testes de migração e concorrência.
