# ADR 0002 — Endereço de escuta configurável

Estado: implementado em 2026-11-25.

## Contexto

O usuário quer acessar a interface de outros dispositivos na rede local. O launcher original escuta apenas em loopback; API e MCP não têm autenticação.

## Decisão

O launcher aceita `HOST` e mantém `127.0.0.1` como padrão. A escolha explícita de `0.0.0.0` faz o servidor escutar em todas as interfaces IPv4. O launcher avisa sobre a ausência de autenticação; o README orienta restringir acesso por firewall. A configuração não altera as proteções de host do MCP nem adiciona autenticação.

## Avaliação de segurança e consequências

A exposição permite que clientes capazes de alcançar a API consultem resultados, enviem e removam trabalhos e consumam recursos. Quando a validação de host do MCP permite acesso, suas ferramentas podem ler arquivos acessíveis ao processo. A opção não oferece isolamento entre usuários, criptografia ou controle de acesso; não é apropriada para redes não confiáveis ou internet sem proteções externas. Loopback permanece o padrão. O microfone em navegador remoto pode exigir HTTPS. Como alternativa mais segura, pode-se manter loopback e usar um túnel autenticado; autenticação integrada fica fora desta mudança.
