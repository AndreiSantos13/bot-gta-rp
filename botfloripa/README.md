# Bot de Gerenciamento de Servidor GTA RP

Um bot completo para gerenciar seu servidor de GTA RP no Discord, incluindo sistema de whitelist visual, moderação, anúncios e sugestões.

![Sorocaba Roleplay](https://i.imgur.com/example.png)

## Funcionalidades

- **Sistema de Whitelist Visual**: Sistema interativo com botões, canais temporários privados e avaliação automática
- **Gerenciamento de Whitelist**: Aprovação/rejeição manual, dashboard administrativo e notificações em canais configuráveis
- **Gerenciamento de Cargos**: Remoção automática do cargo "Turista" e adição do cargo "Morador" para usuários aprovados
- **Sistema de Moderação**: Avisos, banimentos temporários e permanentes, expulsões e silenciamentos
- **Sistema de Anúncios**: Anúncios simples ou personalizados com embeds
- **Sistema de Sugestões**: Envio e gerenciamento de sugestões para o servidor

## Instalação

### Pré-requisitos

- Python 3.10 ou superior
- Biblioteca `discord.py` (2.0 ou superior)
- Biblioteca `python-dotenv`

### Passos para Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/bot-gta-rp.git
   cd bot-gta-rp
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Crie um arquivo `.env` na raiz do projeto com seu token do Discord:
   ```
   DISCORD_TOKEN=seu_token_aqui
   ```

4. Execute o bot:
   ```bash
   python main.py
   ```

## Configuração Inicial

Após adicionar o bot ao seu servidor, use o comando `!setup` para configurar os cargos e canais necessários. Este assistente interativo vai guiar você pelo processo de configuração.

Principais itens para configurar:

1. **Cargos**: 
   - Administrador (permissões totais)
   - Moderador (permissões de moderação)
   - Turista (cargo para novos membros)
   - Morador (cargo para membros aprovados na whitelist)

2. **Canais**:
   - Canal de anúncios
   - Canal de resultados da whitelist
   - Canal para notificações de aprovações
   - Canal para notificações de rejeições

## Sistema de Whitelist

### Configuração da Whitelist

1. Utilize o comando `!allowlist configure` para modificar:
   - Pontuação mínima para aprovação automática
   - Idade mínima da conta para aplicar
   - Ativar/desativar aprovação automática

2. Configure um canal com o botão de whitelist:
   ```
   !allowlist setup_whitelist #canal
   ```

3. Personalize as perguntas no arquivo `config.json`:

```json
"allowlist": {
    "questions": [
        "O que é METAGAMING?",
        "O que é POWERGAMING?",
        ...
    ],
    "correct_answers": [
        "É você usar informações de fora do jogo.",
        "É abusar da mecânica do jogo.",
        ...
    ]
}
```

### Fluxo da Whitelist

1. O usuário clica no botão "Iniciar Whitelist" em um canal público.
2. O bot cria um canal privado temporário ou inicia uma DM.
3. O usuário responde a perguntas sobre regras de RP.
4. O sistema avalia automaticamente as respostas baseado em palavras-chave.
5. Se a pontuação for superior à mínima e auto-aprovação estiver ativada:
   - O usuário é aprovado automaticamente
   - Recebe o cargo de "Morador" e perde o cargo de "Turista"
   - É notificado por DM
6. Se não, a aplicação fica pendente para revisão manual.
7. Administradores podem usar `!allowlist dashboard` para revisar aplicações pendentes.

### Comandos de Whitelist

- `!allowlist dashboard` - Painel administrativo de whitelist
- `!allowlist review <ID>` - Revisar uma aplicação específica
- `!allowlist add @usuário` - Adicionar usuário manualmente à whitelist
- `!allowlist remove @usuário` - Remover usuário da whitelist
- `!allowlist list` - Listar todos os usuários na whitelist
- `!allowlist configure` - Configurar parâmetros do sistema

## Comandos Administrativos

- `!setup` - Assistente de configuração do servidor
- `!reload <módulo>` - Recarregar um módulo específico
- `!restart` - Reiniciar o bot completamente
- `!ping` - Verificar latência do bot
- `!ajuda` - Exibir lista de comandos e ajuda

## Comandos de Moderação

- `!warn @usuário <motivo>` - Adicionar advertência
- `!warnings @usuário` - Mostrar advertências
- `!clearwarnings @usuário` - Limpar advertências
- `!ban @usuário [tempo] <motivo>` - Banir usuário
- `!unban ID <motivo>` - Desbanir usuário
- `!kick @usuário <motivo>` - Expulsar usuário
- `!mute @usuário [tempo] <motivo>` - Silenciar usuário
- `!unmute @usuário <motivo>` - Remover silenciamento

## Suporte

Para obter ajuda ou relatar problemas, abra uma issue no repositório ou entre em contato com o desenvolvedor.

## Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo LICENSE para detalhes.