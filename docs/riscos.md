# Riscos e pendências

Registro inicial em 2026-11-25; prioridades são avaliação técnica, não compromissos de entrega.

| Risco | Impacto e situação | Próxima ação sugerida |
| --- | --- | --- |
| API/MCP sem autenticação | Outros processos locais podem acessar dados e arquivos; exposição de rede amplia o risco. | Manter loopback; projetar autenticação e autorização antes de acesso remoto. |
| Dados persistidos | Transcrições e exportações podem ser sensíveis; exclusão do histórico não remove exportações MCP. | Definir retenção, exclusão e permissões; documentar backups. |
| Fila volátil | Reinício perde trabalhos pendentes e em execução. | Avaliar persistência e recuperação com critérios de produto. |
| Uploads grandes e múltiplos | Até 20 GB por lote podem consumir disco; upload síncrono pode afetar responsividade. | Avaliar cotas, espaço livre e carga real. |
| Dependências com intervalos abertos | Instalações futuras podem variar e introduzir regressões. | Adotar lock reproduzível e política de atualização após escolher plataformas. |
| Qualidade e confiabilidade | Testes simulados não medem reconhecimento, GPU ou usabilidade. | Definir conjunto de avaliação consentido e testes manuais reproduzíveis. |
| Origem e revisão | Repositório sem histórico de commits; não há evidência de revisão anterior. | Registrar revisões e verificações daqui em diante. |
