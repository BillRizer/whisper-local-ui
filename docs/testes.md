# Estratégia de verificação

Instale dependências de desenvolvimento e execute:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

A suíte em `tests/test_app.py` exercita formatos, ciclo de vida do modelo, API, persistência e MCP com transcritor simulado. Não demonstra precisão da transcrição, funcionamento real de CUDA, download real de pesos, gravação no navegador ou segurança completa. Para mudanças nessas áreas, complemente com verificação manual apropriada e registre ambiente, passos e resultado na PR; não inclua áudio privado em fixtures. Para alterações visuais, confira também estados de carregamento e erro em navegador.

Critérios de regressão: rejeição de entrada inválida, preservação do arquivo MCP, limpeza de upload, exportação, persistência e comportamento da fila devem continuar sendo testados quando afetados. Alterações de segurança exigem teste da fronteira de confiança. O CI executa a suíte em CPU com dependências instaladas; não é prova de funcionamento de modelo real ou GPU.
