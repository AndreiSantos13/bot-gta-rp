import os
import json
import logging
import discord
from discord.ext import commands
import asyncio
from dotenv import load_dotenv
from utils.db import setup_database

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("bot")

# Load configuration
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    logger.error("config.json not found. Please create a config file.")
    exit(1)
except json.JSONDecodeError:
    logger.error("config.json is not valid JSON. Please check the format.")
    exit(1)

# Discord Bot setup
# Using minimal intents that don't require privileged access
intents = discord.Intents.default()
intents.message_content = True  # Only enabling message content intent

# For full functionality, enable these intents in Discord Developer Portal
# and then uncomment these lines:
# intents.members = True       # SERVER MEMBERS INTENT
# intents.presences = True     # PRESENCE INTENT

bot = commands.Bot(
    command_prefix=config.get('prefix', '!'),
    intents=intents,
    case_insensitive=True
)

@bot.event
async def on_ready():
    """Event triggered when the bot is ready and connected to Discord"""
    logger.info(f'Logged in as {bot.user.name} - {bot.user.id}')
    
    # Set bot status
    activity_name = config.get('activity_name', 'GTA RP')
    activity_type = getattr(discord.ActivityType, config.get('activity_type', 'playing').lower())
    activity = discord.Activity(type=activity_type, name=activity_name)
    await bot.change_presence(activity=activity)
    
    # Load cogs (modules)
    await load_cogs()
    
    logger.info(f"Bot is ready! Serving {len(bot.guilds)} servers.")

async def load_cogs():
    """Load all cog modules"""
    cogs = [
        'cogs.allowlist',
        'cogs.moderation',
        'cogs.announcements',
        'cogs.suggestions'
    ]
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"Loaded cog: {cog}")
        except Exception as e:
            logger.error(f"Error loading cog {cog}: {str(e)}")

@bot.event
async def on_command_error(ctx, error):
    """Tratamento global de erros de comandos"""
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ **Argumento obrigatório faltando:** {error.param.name}")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ **Sem permissão:** Você não tem permissão para usar este comando.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"❌ **Permissões necessárias:** Preciso das seguintes permissões para executar este comando: {', '.join(error.missing_permissions)}")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏱️ **Comando em cooldown:** Tente novamente em {error.retry_after:.2f} segundos.")
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("❌ **Acesso negado:** Você não tem permissão para usar este comando.")
    else:
        logger.error(f"Erro de comando não tratado: {str(error)}")
        await ctx.send(f"❌ **Ocorreu um erro:** {str(error)}")

@bot.command(name="ping")
async def ping(ctx):
    """Comando simples para verificar se o bot está respondendo"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latência do bot: {latency}ms")

@bot.command(name="reload")
@commands.has_permissions(administrator=True)
async def reload_cog(ctx, cog: str):
    """Recarrega um módulo específico do bot"""
    try:
        await bot.reload_extension(f"cogs.{cog}")
        await ctx.send(f"✅ Módulo '{cog}' foi recarregado com sucesso.")
    except Exception as e:
        await ctx.send(f"❌ Falha ao recarregar módulo '{cog}': {str(e)}")
        logger.error(f"Erro ao recarregar módulo {cog}: {str(e)}")

@bot.command(name="restart")
@commands.has_permissions(administrator=True)
async def restart_bot(ctx):
    """Reinicia o bot inteiro (requer acesso ao sistema)"""
    await ctx.send("🔄 Reiniciando o bot... Isso pode levar alguns segundos.")
    try:
        # Salvando qualquer dado pendente
        await ctx.send("✅ Bot será reiniciado. Até logo!")
        
        # Fechando o bot
        await bot.close()
        
        # O sistema de hospedagem deve reiniciar o bot automaticamente
    except Exception as e:
        await ctx.send(f"❌ Erro ao tentar reiniciar: {str(e)}")
        logger.error(f"Erro ao reiniciar: {str(e)}")

@bot.command(name="ajuda", aliases=["help"])
async def help_command(ctx, modulo=None):
    """Exibe ajuda sobre os comandos do bot"""
    
    if modulo is None:
        # Exibe ajuda geral
        embed = discord.Embed(
            title="🤖 Ajuda do Bot de Gerenciamento",
            description="Bem-vindo à ajuda do bot de gerenciamento de servidor GTA RP. Abaixo estão os módulos disponíveis.",
            color=0x3498db
        )
        
        embed.add_field(
            name="📋 Módulos",
            value=(
                "**`!ajuda whitelist`** - Sistema de whitelist\n"
                "**`!ajuda moderação`** - Comandos de moderação\n"
                "**`!ajuda anúncios`** - Sistema de anúncios\n"
                "**`!ajuda sugestões`** - Sistema de sugestões\n"
                "**`!ajuda admin`** - Comandos administrativos"
            ),
            inline=False
        )
        
        embed.add_field(
            name="ℹ️ Comandos Básicos",
            value=(
                "**`!ping`** - Verifica se o bot está funcionando\n"
                "**`!ajuda`** - Exibe esta mensagem de ajuda\n"
            ),
            inline=False
        )
        
        embed.set_footer(text="Use !ajuda <módulo> para ver comandos específicos")
    
    elif modulo.lower() in ["whitelist", "wl"]:
        # Ajuda sobre o sistema de whitelist
        embed = discord.Embed(
            title="📝 Sistema de Whitelist",
            description="Comandos para gerenciar o sistema de whitelist do servidor.",
            color=0x3498db
        )
        
        embed.add_field(
            name="⚙️ Configuração",
            value=(
                "**`!allowlist configure`** - Ver ou modificar configurações de whitelist\n"
                "**`!allowlist setup_whitelist #canal`** - Configura um canal com botão de whitelist"
            ),
            inline=False
        )
        
        embed.add_field(
            name="👮 Administração",
            value=(
                "**`!allowlist dashboard`** - Painel de status da whitelist\n"
                "**`!allowlist review <ID>`** - Revisa uma aplicação pendente\n"
                "**`!allowlist add @usuário`** - Adiciona usuário à whitelist\n"
                "**`!allowlist remove @usuário`** - Remove usuário da whitelist\n"
                "**`!allowlist list`** - Lista usuários na whitelist"
            ),
            inline=False
        )
        
        embed.set_footer(text="Todos os comandos requerem permissões de administrador ou moderador")
        
    elif modulo.lower() in ["moderação", "moderacao", "mod"]:
        # Ajuda sobre comandos de moderação
        embed = discord.Embed(
            title="🛡️ Comandos de Moderação",
            description="Ferramentas para moderação do servidor.",
            color=0xe74c3c
        )
        
        embed.add_field(
            name="⚠️ Avisos",
            value=(
                "**`!warn @usuário <motivo>`** - Adiciona advertência\n"
                "**`!warnings @usuário`** - Mostra advertências\n"
                "**`!clearwarnings @usuário`** - Limpa advertências"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🚫 Punições",
            value=(
                "**`!ban @usuário [tempo] <motivo>`** - Bane usuário (temporariamente ou permanentemente)\n"
                "**`!unban ID_usuário <motivo>`** - Remove banimento\n"
                "**`!kick @usuário <motivo>`** - Expulsa usuário\n"
                "**`!mute @usuário [tempo] <motivo>`** - Silencia usuário\n"
                "**`!unmute @usuário <motivo>`** - Remove silenciamento"
            ),
            inline=False
        )
        
    elif modulo.lower() in ["anuncios", "anúncios", "anuncio", "anúncio"]:
        # Ajuda sobre sistema de anúncios
        embed = discord.Embed(
            title="📢 Sistema de Anúncios",
            description="Comandos para enviar anúncios no servidor.",
            color=0xf1c40f
        )
        
        embed.add_field(
            name="📣 Comandos",
            value=(
                "**`!announce <mensagem>`** - Envia anúncio simples\n"
                "**`!create_embed`** - Cria anúncio personalizado com embed"
            ),
            inline=False
        )
        
    elif modulo.lower() in ["sugestões", "sugestoes", "sugestão", "sugestao"]:
        # Ajuda sobre sistema de sugestões
        embed = discord.Embed(
            title="💡 Sistema de Sugestões",
            description="Comandos para gerenciar sugestões do servidor.",
            color=0x2ecc71
        )
        
        embed.add_field(
            name="👥 Comandos para Usuários",
            value=(
                "**`!suggest <sugestão>`** - Envia uma sugestão"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚙️ Comandos para Staff",
            value=(
                "**`!approve_suggestion <ID> [comentário]`** - Aprova uma sugestão\n"
                "**`!reject_suggestion <ID> [motivo]`** - Rejeita uma sugestão\n"
                "**`!consider_suggestion <ID> [comentário]`** - Marca sugestão como sendo considerada\n"
                "**`!implement_suggestion <ID> [comentário]`** - Marca sugestão como implementada"
            ),
            inline=False
        )
        
    elif modulo.lower() in ["admin", "administrador", "administração", "administracao"]:
        # Ajuda sobre comandos administrativos
        embed = discord.Embed(
            title="⚙️ Comandos Administrativos",
            description="Comandos para administração do bot e servidor.",
            color=0x9b59b6
        )
        
        embed.add_field(
            name="🔧 Comandos",
            value=(
                "**`!setup`** - Assistente interativo de configuração do servidor\n"
                "**`!reload <cog>`** - Recarrega um módulo específico do bot\n"
                "**`!restart`** - Reinicia o bot completamente"
            ),
            inline=False
        )
        
    else:
        # Módulo não reconhecido
        embed = discord.Embed(
            title="❓ Módulo Não Encontrado",
            description=f"O módulo '{modulo}' não foi reconhecido. Use `!ajuda` para ver os módulos disponíveis.",
            color=0xe74c3c
        )
    
    await ctx.send(embed=embed)

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_server(ctx):
    """Guia interativo para configurar o servidor"""
    # Iniciar o assistente de configuração
    await ctx.send("📝 **Assistente de Configuração do Servidor**\n\nVamos configurar seu servidor passo a passo. Responda às perguntas conforme elas aparecerem.")
    
    # Função para esperar resposta
    async def get_response(question, timeout=60):
        await ctx.send(question)
        try:
            response = await bot.wait_for(
                'message', 
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
                timeout=timeout
            )
            return response.content
        except asyncio.TimeoutError:
            await ctx.send("⏱️ Tempo esgotado. Configuração cancelada.")
            return None
    
    # Configuração do nome do servidor
    server_name = await get_response("1️⃣ Qual é o nome do seu servidor de GTA RP?")
    if not server_name:
        return
    
    # Configuração de cargos
    await ctx.send("⚙️ **Configuração de Cargos**\nAgora vamos configurar os cargos principais.")
    
    # Cargo de Admin
    admin_input = await get_response("2️⃣ Mencione o cargo de Administrador (@cargo):")
    if not admin_input:
        return
    
    # Cargo de Moderador
    mod_input = await get_response("3️⃣ Mencione o cargo de Moderador (@cargo):")
    if not mod_input:
        return
    
    # Cargo de Turista
    tourist_input = await get_response("4️⃣ Mencione o cargo de Turista (usuários não aprovados) (@cargo):")
    if not tourist_input:
        return
    
    # Cargo de Morador
    resident_input = await get_response("5️⃣ Mencione o cargo de Morador (usuários aprovados) (@cargo):")
    if not resident_input:
        return
    
    # Configuração de canais
    await ctx.send("📢 **Configuração de Canais**\nAgora vamos configurar os canais principais.")
    
    # Canal de anúncios
    announcements_input = await get_response("6️⃣ Mencione o canal de anúncios (#canal):")
    if not announcements_input:
        return
    
    # Canal de resultados da whitelist
    results_input = await get_response("7️⃣ Mencione o canal para resultados de whitelist (#canal):")
    if not results_input:
        return
    
    # Canal de whitelist aprovados
    approved_input = await get_response("8️⃣ Mencione o canal para notificações de whitelist aprovadas (#canal):")
    if not approved_input:
        return
    
    # Canal de whitelist reprovados
    rejected_input = await get_response("9️⃣ Mencione o canal para notificações de whitelist reprovadas (#canal):")
    if not rejected_input:
        return
    
    # Extrai IDs dos cargos e canais mencionados
    try:
        # Extrai IDs dos cargos
        admin_id = int(admin_input.strip('<@&>'))
        mod_id = int(mod_input.strip('<@&>'))
        tourist_id = int(tourist_input.strip('<@&>'))
        resident_id = int(resident_input.strip('<@&>'))
        
        # Extrai IDs dos canais
        announcements_id = int(announcements_input.strip('<#>'))
        results_id = int(results_input.strip('<#>'))
        approved_id = int(approved_input.strip('<#>'))
        rejected_id = int(rejected_input.strip('<#>'))
        
        # Carrega a configuração atual
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Atualiza a configuração
        config['server_name'] = server_name
        
        # Atualiza cargos
        config['roles']['admin'] = admin_id
        config['roles']['moderator'] = mod_id
        config['roles']['tourist'] = tourist_id
        config['roles']['resident'] = resident_id
        config['roles']['allowed'] = resident_id  # Usa o mesmo ID para compatibilidade
        
        # Atualiza canais
        config['channels']['announcements'] = announcements_id
        config['channels']['allowlist_results'] = results_id
        config['channels']['allowlist_approved'] = approved_id
        config['channels']['allowlist_rejected'] = rejected_id
        
        # Salva a configuração
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)
        
        await ctx.send("✅ **Configuração concluída com sucesso!**\nAs configurações do servidor foram atualizadas.")
        
    except ValueError:
        await ctx.send("❌ **Erro de formato**\nAlgumas entradas não eram menções válidas. Use @cargo para cargos e #canal para canais.")
    except Exception as e:
        await ctx.send(f"❌ **Erro inesperado**\n{str(e)}")
        logger.error(f"Erro na configuração: {str(e)}")

if __name__ == "__main__":
    # Initialize database
    setup_database()
    
    # Start the bot
    bot_token = os.getenv("DISCORD_TOKEN")
    if not bot_token:
        logger.error("No Discord token found. Set the DISCORD_TOKEN environment variable.")
        exit(1)
    
    bot.run(bot_token)
