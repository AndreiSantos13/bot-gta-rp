import discord
from discord.ext import commands
import asyncio
import json
import logging
from datetime import datetime, timedelta
import sqlite3
from discord import app_commands
from discord.ui import Button, View

from utils.db import (
    add_to_allowlist, remove_from_allowlist, check_allowlist, 
    update_allowlist_status, add_temp_channel, remove_temp_channel
)
from utils.helpers import (
    create_embed, load_config, can_use_allowlist_commands,
    format_time_difference
)

logger = logging.getLogger("bot.allowlist")

class WhitelistReviewButtons(discord.ui.View):
    def __init__(self, user_id, bot):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.bot = bot
        
        # Botão de aprovar
        self.approve_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Aprovar Whitelist",
            custom_id=f"approve_whitelist_{user_id}"
        )
        self.approve_button.callback = self.approve_callback
        
        # Botão de rejeitar
        self.reject_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Reprovar Whitelist",
            custom_id=f"reject_whitelist_{user_id}"
        )
        self.reject_button.callback = self.reject_callback
        
        # Adiciona os botões à view
        self.add_item(self.approve_button)
        self.add_item(self.reject_button)
        
        # Menu de seleção para motivo de rejeição
        self.reject_reasons = discord.ui.Select(
            placeholder="Selecione um motivo para recusar...",
            custom_id=f"reject_reason_{user_id}",
            options=[
                discord.SelectOption(label="Respostas incorretas", value="incorrect", description="Muitas respostas incorretas"),
                discord.SelectOption(label="Respostas vagas", value="vague", description="Respostas muito vagas ou curtas"),
                discord.SelectOption(label="Não entende RP", value="norpknowledge", description="Não demonstra conhecimento de RP"),
                discord.SelectOption(label="Comportamento inadequado", value="behavior", description="Comportamento inadequado durante a whitelist"),
                discord.SelectOption(label="Outro motivo", value="other", description="Outro motivo")
            ]
        )
        self.reject_reasons.callback = self.reject_reason_callback
        self.add_item(self.reject_reasons)
    
    async def approve_callback(self, interaction: discord.Interaction):
        """Aprova a whitelist do usuário"""
        # Obtém o usuário
        user = interaction.client.get_user(self.user_id)
        if not user:
            await interaction.response.send_message("Usuário não encontrado.", ephemeral=True)
            return
            
        # Aprova a whitelist
        try:
            update_allowlist_status(self.user_id, "approved", interaction.user.id)
            
            # Adiciona o cargo de aprovado e remove o de turista
            for guild in self.bot.guilds:
                member = guild.get_member(self.user_id)
                if member:
                    # Remove cargo de turista
                    config = load_config()
                    tourist_role_id = config.get('roles', {}).get('tourist')
                    if tourist_role_id:
                        tourist_role = guild.get_role(tourist_role_id)
                        if tourist_role and tourist_role in member.roles:
                            await member.remove_roles(tourist_role)
                    
                    # Adiciona cargo de morador/residente
                    resident_role_id = config.get('roles', {}).get('resident')
                    if resident_role_id:
                        resident_role = guild.get_role(resident_role_id)
                        if resident_role:
                            await member.add_roles(resident_role)
                            
                    # Também adiciona o cargo de "allowed" por compatibilidade
                    allowed_role_id = config.get('roles', {}).get('allowed')
                    if allowed_role_id and allowed_role_id != resident_role_id:
                        allowed_role = guild.get_role(allowed_role_id)
                        if allowed_role:
                            await member.add_roles(allowed_role)
            
            # Envia mensagem de confirmação
            await interaction.response.send_message(
                f"Whitelist de {user.mention} foi aprovada manualmente por {interaction.user.mention}.",
                ephemeral=False
            )
            
            # Envia mensagem ao usuário
            try:
                dm_channel = await user.create_dm()
                await dm_channel.send(
                    embed=discord.Embed(
                        title="✅ Whitelist Aprovada",
                        description=f"Sua whitelist foi aprovada por {interaction.user}. Você pode agora acessar o servidor!",
                        color=0x2ecc71
                    )
                )
            except:
                pass
                
            # Atualiza a mensagem para desabilitar os botões
            await interaction.message.edit(view=None, content=f"Whitelist aprovada por {interaction.user.mention}")
            
            # Notifica canais apropriados
            cog = self.bot.get_cog("Allowlist")
            await cog._notify_approved_channels(user, interaction.user)
            
        except Exception as e:
            logger.error(f"Erro ao aprovar whitelist: {e}")
            await interaction.response.send_message(f"Erro ao aprovar whitelist: {e}", ephemeral=True)
    
    async def reject_callback(self, interaction: discord.Interaction):
        """Rejeita a whitelist do usuário"""
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("Por favor, selecione um motivo para rejeição no menu abaixo.", ephemeral=True)
    
    async def reject_reason_callback(self, interaction: discord.Interaction):
        """Processa o motivo da rejeição"""
        reason = self.reject_reasons.values[0]
        reason_text = "Motivo não especificado"
        
        # Mapeia o valor para texto
        reason_map = {
            "incorrect": "Muitas respostas incorretas",
            "vague": "Respostas muito vagas ou curtas",
            "norpknowledge": "Não demonstra conhecimento de RP",
            "behavior": "Comportamento inadequado durante a whitelist",
            "other": "Outro motivo"
        }
        
        if reason in reason_map:
            reason_text = reason_map[reason]
        
        # Obtém o usuário
        user = interaction.client.get_user(self.user_id)
        if not user:
            await interaction.response.send_message("Usuário não encontrado.", ephemeral=True)
            return
            
        # Rejeita a whitelist
        try:
            # Atualiza o status
            update_allowlist_status(self.user_id, "rejected", interaction.user.id)
            
            # Envia mensagem de confirmação
            await interaction.response.send_message(
                f"Whitelist de {user.mention} foi rejeitada por {interaction.user.mention}.\nMotivo: {reason_text}",
                ephemeral=False
            )
            
            # Envia mensagem ao usuário
            try:
                dm_channel = await user.create_dm()
                await dm_channel.send(
                    embed=discord.Embed(
                        title="❌ Whitelist Reprovada",
                        description=f"Sua whitelist foi reprovada por {interaction.user}.\nMotivo: {reason_text}\n\nVocê pode tentar novamente mais tarde.",
                        color=0xe74c3c
                    )
                )
            except:
                pass
                
            # Atualiza a mensagem para desabilitar os botões
            await interaction.message.edit(view=None, content=f"Whitelist rejeitada por {interaction.user.mention}")
            
            # Notifica canais apropriados
            cog = self.bot.get_cog("Allowlist")
            await cog._notify_rejected_channels(user, interaction.user, reason_text)
            
        except Exception as e:
            logger.error(f"Erro ao rejeitar whitelist: {e}")
            await interaction.response.send_message(f"Erro ao rejeitar whitelist: {e}", ephemeral=True)


class WhitelistButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Iniciar Whitelist",
            custom_id="iniciar_whitelist"
        )
    
    async def callback(self, interaction: discord.Interaction):
        # Inicia o processo de whitelist
        # Verificamos se o usuário já está na whitelist
        existing_entry = check_allowlist(interaction.user.id)
        
        if existing_entry:
            if existing_entry['status'] == 'approved':
                await interaction.response.send_message(
                    embed=create_embed(
                        "Já Aprovado", 
                        "Você já está na whitelist!", 
                        color="success"
                    ),
                    ephemeral=True
                )
                return
            elif existing_entry['status'] == 'pending':
                await interaction.response.send_message(
                    embed=create_embed(
                        "Aplicação Pendente", 
                        "Sua aplicação para whitelist já está pendente de revisão.", 
                        color="info"
                    ),
                    ephemeral=True
                )
                return
        
        # Verificar idade da conta
        config = load_config()
        min_age_days = config.get('allowlist', {}).get('min_account_age_days', 0)
        
        created_at = interaction.user.created_at
        now = datetime.now().astimezone()
        account_age = now - created_at
        
        if account_age.days < min_age_days:
            await interaction.response.send_message(
                embed=create_embed(
                    "Conta Muito Nova", 
                    f"Sua conta do Discord precisa ter pelo menos {min_age_days} dias. Sua conta tem {account_age.days} dias.",
                    color="error"
                ),
                ephemeral=True
            )
            return
        
        # Criamos um canal privado para o usuário
        try:
            guild = interaction.guild
            user = interaction.user
            
            # Obter categoria para canais de whitelist
            category_id = config.get('channels', {}).get('allowlist_category')
            category = None
            if category_id:
                category = guild.get_channel(category_id)
            
            # Criar permissões do canal privado
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            # Adicionar permissões para cargos admin/mod
            admin_role_id = config.get('roles', {}).get('admin')
            mod_role_id = config.get('roles', {}).get('moderator')
            
            if admin_role_id:
                admin_role = guild.get_role(admin_role_id)
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            if mod_role_id:
                mod_role = guild.get_role(mod_role_id)
                if mod_role:
                    overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # Criar o canal
            channel_name = f"wl-{user.name}-{user.discriminator if hasattr(user, 'discriminator') else ''}"
            channel = await guild.create_text_channel(
                channel_name,
                overwrites=overwrites,
                category=category,
                topic=f"Whitelist para {user.display_name}"
            )
            
            # Registrar canal temporário no banco de dados
            add_temp_channel(channel.id, user.id, "whitelist")
            
            # Informar ao usuário
            await interaction.response.send_message(
                embed=create_embed(
                    "Whitelist Iniciada", 
                    f"Canal criado para sua whitelist: {channel.mention}\nPor favor, vá até lá para continuar o processo.",
                    color="success"
                ),
                ephemeral=True
            )
            
            # Iniciar o processo de whitelist no canal
            cog = interaction.client.get_cog("Allowlist")
            await cog.start_whitelist_channel(user, channel)
            
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=create_embed(
                    "Erro de Permissão", 
                    "Não tenho permissão para criar canais. Por favor, informe a um administrador.",
                    color="error"
                ),
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Erro ao criar canal para whitelist: {e}")
            await interaction.response.send_message(
                embed=create_embed(
                    "Erro", 
                    "Ocorreu um erro ao iniciar sua whitelist. Por favor, tente novamente mais tarde.",
                    color="error"
                ),
                ephemeral=True
            )


class Allowlist(commands.Cog):
    """Handles the allowlist system for the server"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        self.pending_applications = {}
        self.user_scores = {}
    
    @commands.group(name="allowlist", aliases=["wl"])
    async def allowlist(self, ctx):
        """Command group for allowlist management"""
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand. Use `!help allowlist` for more information.")
    
    @allowlist.command(name="apply")
    async def apply(self, ctx):
        """Start the allowlist application process"""
        # Check if user is already in allowlist
        existing_entry = check_allowlist(ctx.author.id)
        
        if existing_entry:
            if existing_entry['status'] == 'approved':
                await ctx.send(
                    embed=create_embed(
                        "Already Approved", 
                        "You are already on the allowlist!", 
                        color="success"
                    )
                )
                return
            elif existing_entry['status'] == 'pending':
                await ctx.send(
                    embed=create_embed(
                        "Application Pending", 
                        "Your allowlist application is already pending review.", 
                        color="info"
                    )
                )
                return
            elif existing_entry['status'] == 'rejected':
                # Allow reapplying if previously rejected
                pass
        
        # Check account age requirement
        min_age_days = self.config.get('allowlist', {}).get('min_account_age_days', 0)
        
        # Converter para datas do mesmo tipo (aware)
        created_at = ctx.author.created_at
        now = datetime.now().astimezone() # Converter para aware datetime
        account_age = now - created_at
        
        if account_age.days < min_age_days:
            await ctx.send(
                embed=create_embed(
                    "Account Too New", 
                    f"Your Discord account needs to be at least {min_age_days} days old to apply. Your account is {account_age.days} days old.",
                    color="error"
                )
            )
            return
        
        # Create a private channel for the application
        try:
            # Get the allowlist category
            category_id = self.config.get('channels', {}).get('allowlist_category')
            category = None
            
            if category_id:
                category = ctx.guild.get_channel(category_id)
            
            # Create private channel
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                ctx.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            # Add admin/mod role permissions
            admin_role_id = self.config.get('roles', {}).get('admin')
            mod_role_id = self.config.get('roles', {}).get('moderator')
            
            if admin_role_id:
                admin_role = ctx.guild.get_role(admin_role_id)
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            if mod_role_id:
                mod_role = ctx.guild.get_role(mod_role_id)
                if mod_role:
                    overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            channel_name = f"allowlist-{ctx.author.name}-{ctx.author.discriminator}"
            channel = await ctx.guild.create_text_channel(
                channel_name,
                overwrites=overwrites,
                category=category,
                topic=f"Allowlist application for {ctx.author.display_name}"
            )
            
            # Save temp channel to database
            add_temp_channel(channel.id, ctx.author.id, "allowlist")
            
            # Send confirmation message
            await ctx.send(
                embed=create_embed(
                    "Application Started", 
                    f"Your allowlist application has been started in {channel.mention}",
                    color="success"
                )
            )
            
            # Start the application process
            await self._process_application(ctx.author, channel)
            
        except discord.errors.Forbidden:
            await ctx.send(
                embed=create_embed(
                    "Error", 
                    "I don't have permission to create channels. Please contact an administrator.",
                    color="error"
                )
            )
        except Exception as e:
            logger.error(f"Error creating application channel: {e}")
            await ctx.send(
                embed=create_embed(
                    "Error", 
                    "An error occurred while setting up your application. Please try again later.",
                    color="error"
                )
            )
    
    async def _process_application(self, user, channel):
        """Process an allowlist application in the given channel"""
        # Send welcome message
        await channel.send(
            embed=create_embed(
                "Allowlist Application", 
                f"Welcome {user.mention}! Please answer the following questions to apply for the allowlist."
                f"\n\nYou will have 5 minutes to answer each question. Type `cancel` at any time to cancel the application.",
                color="info"
            )
        )
        
        await asyncio.sleep(2)  # Small delay
        
        # Get questions from config
        questions = self.config.get('allowlist', {}).get('questions', [])
        
        if not questions:
            await channel.send(
                embed=create_embed(
                    "Error", 
                    "No questions are configured for the allowlist. Please contact an administrator.",
                    color="error"
                )
            )
            return
        
        # Store answers
        answers = []
        
        # Ask each question
        for i, question in enumerate(questions):
            question_embed = create_embed(
                f"Question {i+1}/{len(questions)}", 
                question,
                color="info"
            )
            await channel.send(embed=question_embed)
            
            # Wait for response
            try:
                response_msg = await self.bot.wait_for(
                    'message',
                    check=lambda m: m.author == user and m.channel == channel,
                    timeout=300  # 5 minutes
                )
                
                if response_msg.content.lower() == 'cancel':
                    await channel.send(
                        embed=create_embed(
                            "Application Cancelled", 
                            "You have cancelled your allowlist application.",
                            color="error"
                        )
                    )
                    # Schedule channel deletion
                    await asyncio.sleep(5)
                    await channel.delete()
                    return
                
                # Store the answer
                answers.append({
                    'question': question,
                    'answer': response_msg.content
                })
                
            except asyncio.TimeoutError:
                await channel.send(
                    embed=create_embed(
                        "Timeout", 
                        "You took too long to respond. Your application has been cancelled.",
                        color="error"
                    )
                )
                # Schedule channel deletion
                await asyncio.sleep(5)
                await channel.delete()
                return
        
        # Application completed
        await channel.send(
            embed=create_embed(
                "Application Submitted", 
                "Thank you for submitting your application! It will be reviewed by staff as soon as possible.",
                color="success"
            )
        )
        
        # Save application to database
        try:
            answers_json = json.dumps(answers)
            add_to_allowlist(user.id, status="pending", answers=answers_json)
            
            # If auto-approve is enabled, approve immediately
            if self.config.get('allowlist', {}).get('auto_approve', False):
                update_allowlist_status(user.id, "approved", self.bot.user.id)
                
                # Add allowed role if configured
                allowed_role_id = self.config.get('roles', {}).get('allowed')
                if allowed_role_id:
                    allowed_role = channel.guild.get_role(allowed_role_id)
                    if allowed_role:
                        await user.add_roles(allowed_role)
                
                await channel.send(
                    embed=create_embed(
                        "Application Approved", 
                        "Your allowlist application has been automatically approved!",
                        color="success"
                    )
                )
                
                # Schedule channel deletion
                await asyncio.sleep(30)
                await channel.delete()
            else:
                # Notify staff that a new application is pending
                staff_msg = create_embed(
                    "New Application", 
                    f"{user.mention} has submitted an allowlist application. Use `!allowlist review {user.id}` to review it.",
                    color="info"
                )
                
                # Keep the channel open for staff to review
                await channel.send(
                    content="@here",  # Ping staff
                    embed=staff_msg
                )
        except Exception as e:
            logger.error(f"Error saving application: {e}")
            await channel.send(
                embed=create_embed(
                    "Error", 
                    "An error occurred while saving your application. Please try again later.",
                    color="error"
                )
            )
    
    @allowlist.command(name="add")
    @commands.check(can_use_allowlist_commands)
    async def add(self, ctx, user: discord.Member, *, reason="No reason provided"):
        """Add a user to the allowlist"""
        # Check if the user is already on the allowlist
        existing_entry = check_allowlist(user.id)
        
        if existing_entry and existing_entry['status'] == 'approved':
            await ctx.send(
                embed=create_embed(
                    "Error", 
                    f"{user.mention} is already on the allowlist!",
                    color="error"
                )
            )
            return
        
        # Add to allowlist and approve
        try:
            answers = json.dumps([{"question": "Direct Addition", "answer": reason}])
            add_to_allowlist(user.id, ctx.author.id, "approved", answers)
            
            # Add allowed role if configured
            allowed_role_id = self.config.get('roles', {}).get('allowed')
            if allowed_role_id:
                allowed_role = ctx.guild.get_role(allowed_role_id)
                if allowed_role:
                    await user.add_roles(allowed_role)
            
            await ctx.send(
                embed=create_embed(
                    "User Added", 
                    f"{user.mention} has been added to the allowlist by {ctx.author.mention}.",
                    color="success"
                )
            )
        except Exception as e:
            logger.error(f"Error adding user to allowlist: {e}")
            await ctx.send(
                embed=create_embed(
                    "Error", 
                    f"An error occurred: {str(e)}",
                    color="error"
                )
            )
    
    @allowlist.command(name="remove")
    @commands.check(can_use_allowlist_commands)
    async def remove(self, ctx, user: discord.Member):
        """Remove a user from the allowlist"""
        # Check if the user is on the allowlist
        existing_entry = check_allowlist(user.id)
        
        if not existing_entry or existing_entry['status'] != 'approved':
            await ctx.send(
                embed=create_embed(
                    "Error", 
                    f"{user.mention} is not on the allowlist!",
                    color="error"
                )
            )
            return
        
        # Remove from allowlist
        try:
            remove_from_allowlist(user.id)
            
            # Remove allowed role if configured
            allowed_role_id = self.config.get('roles', {}).get('allowed')
            if allowed_role_id:
                allowed_role = ctx.guild.get_role(allowed_role_id)
                if allowed_role and allowed_role in user.roles:
                    await user.remove_roles(allowed_role)
            
            await ctx.send(
                embed=create_embed(
                    "User Removed", 
                    f"{user.mention} has been removed from the allowlist by {ctx.author.mention}.",
                    color="success"
                )
            )
        except Exception as e:
            logger.error(f"Error removing user from allowlist: {e}")
            await ctx.send(
                embed=create_embed(
                    "Error", 
                    f"An error occurred: {str(e)}",
                    color="error"
                )
            )
    
    @allowlist.command(name="check")
    @commands.check(can_use_allowlist_commands)
    async def check_user(self, ctx, user: discord.Member):
        """Check if a user is on the allowlist"""
        # Get allowlist entry
        entry = check_allowlist(user.id)
        
        if not entry:
            await ctx.send(
                embed=create_embed(
                    "Allowlist Check", 
                    f"{user.mention} is not on the allowlist.",
                    color="error"
                )
            )
            return
        
        # Format the response based on status
        if entry['status'] == 'approved':
            # Get the approver info if available
            approver_info = "Unknown"
            if entry['approved_by']:
                approver = ctx.guild.get_member(entry['approved_by'])
                if approver:
                    approver_info = approver.mention
            
            await ctx.send(
                embed=create_embed(
                    "Allowlist Check", 
                    f"{user.mention} is on the allowlist.",
                    color="success",
                    fields=[
                        {"name": "Status", "value": "Approved", "inline": True},
                        {"name": "Approved By", "value": approver_info, "inline": True},
                        {"name": "Approved At", "value": entry['approved_at'] or "Unknown", "inline": True}
                    ]
                )
            )
        elif entry['status'] == 'pending':
            await ctx.send(
                embed=create_embed(
                    "Allowlist Check", 
                    f"{user.mention} has a pending allowlist application.",
                    color="warning"
                )
            )
        else:
            await ctx.send(
                embed=create_embed(
                    "Allowlist Check", 
                    f"{user.mention} is not on the allowlist (status: {entry['status']}).",
                    color="error"
                )
            )
    
    @allowlist.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup_whitelist(self, ctx, channel: discord.TextChannel = None):
        """Cria o painel de whitelist com botão em um canal específico"""
        if channel is None:
            channel = ctx.channel
            
        server_name = self.config.get('allowlist', {}).get('server_name', 'GTA RP Server')
        
        # Cria o embed de boas-vindas para whitelist
        embed = discord.Embed(
            title=f"Sistema de whitelist - {server_name}",
            description="Clique no botão para iniciar sua whitelist, após sua aprovação seu passaporte será liberado na cidade!",
            color=0x2F3136
        )
        
        # Adiciona campos de observações
        embed.add_field(
            name="Observações:",
            value=(
                "• Lembre-se que será necessário ter o passaporte em mãos. Para obter seu passaporte você deve se conectar no servidor usando a sala 📋 Sem acesso.\n"
                "• Você terá em média 1 minuto para responder cada questão.\n"
                "• Caso você reprove terá que refazer sua whitelist."
            ),
            inline=False
        )
        
        # Adiciona o logotipo do servidor como imagem
        logo_url = self.config.get('allowlist', {}).get('server_logo_url')
        if logo_url:
            embed.set_image(url=logo_url)
            
        # Adiciona rodapé
        embed.set_footer(text=f"{server_name} © Todos os direitos reservados")
        
        # Cria o botão de iniciar whitelist
        view = discord.ui.View(timeout=None)
        view.add_item(WhitelistButton())
        
        # Envia a mensagem com o botão
        await channel.send(embed=embed, view=view)
        await ctx.send("Painel de whitelist configurado com sucesso!")
        
    async def start_whitelist_channel(self, user, channel):
        """Inicia o processo de whitelist no canal privado"""
        # Obtém o nome do servidor
        server_name = self.config.get('allowlist', {}).get('server_name', 'GTA RP Server')
        
        # Cria o embed de boas-vindas
        embed = discord.Embed(
            title=f"Sistema de Whitelist - {server_name}",
            description=(
                f"Bem-vindo(a) à whitelist do {server_name}, {user.mention}!\n\n"
                "Você terá 60 segundos para responder cada pergunta.\n"
                "Leia com atenção antes de responder.\n"
                "Boa sorte!"
            ),
            color=0x3498db
        )
        
        # Adiciona observações importantes
        embed.add_field(
            name="Observações:",
            value=(
                "• Lembre-se que será necessário ter o passaporte em mãos.\n"
                "• Você terá em média 1 minuto para responder cada questão.\n"
                "• Caso você reprove terá que refazer sua whitelist."
            ),
            inline=False
        )
        
        # Adiciona o logotipo do servidor como imagem
        logo_url = self.config.get('allowlist', {}).get('server_logo_url')
        if logo_url:
            embed.set_image(url=logo_url)
            
        # Adiciona rodapé
        embed.set_footer(text=f"{server_name} © Todos os direitos reservados")
        
        try:
            # Envia a mensagem de boas-vindas
            await channel.send(embed=embed)
            
            # Inicia o questionário após pequeno delay
            await asyncio.sleep(3)
            await self._process_whitelist_questions(user, channel, in_channel=True)
        except Exception as e:
            logger.error(f"Erro ao iniciar whitelist no canal: {e}")
            await channel.send(
                embed=create_embed(
                    "Erro", 
                    "Ocorreu um erro ao iniciar o processo de whitelist. Por favor, tente novamente mais tarde.",
                    color="error"
                )
            )
            
    async def start_whitelist_dm(self, user):
        """Inicia o processo de whitelist por DM"""
        # Vamos enviar uma mensagem informativa primeiro
        server_name = self.config.get('allowlist', {}).get('server_name', 'GTA RP Server')
        
        # Cria o embed de boas-vindas
        embed = discord.Embed(
            title=f"Whitelist {server_name}",
            description=(
                f"Bem-vindo(a) à whitelist do {server_name}!\n\n"
                "Você terá 60 segundos para responder cada pergunta.\n"
                "Leia com atenção antes de responder.\n"
                "Boa sorte!"
            ),
            color=0x3498db
        )
        
        try:
            # Envia a mensagem de boas-vindas
            dm_channel = await user.create_dm()
            await dm_channel.send(embed=embed)
            
            # Inicia o questionário
            await self._process_whitelist_questions(user, dm_channel)
        except discord.Forbidden:
            logger.error(f"Não foi possível enviar DM para {user}")
            return None
        except Exception as e:
            logger.error(f"Erro ao iniciar whitelist por DM: {e}")
            return None
    
    async def _process_whitelist_questions(self, user, channel, in_channel=False):
        """Processa as perguntas da whitelist em formato visual"""
        questions = self.config.get('allowlist', {}).get('questions', [])
        correct_answers = self.config.get('allowlist', {}).get('correct_answers', [])
        
        if not questions or len(questions) != len(correct_answers):
            await channel.send(
                embed=create_embed(
                    "Erro", 
                    "A configuração da whitelist está incorreta. Por favor, informe a um administrador.",
                    color="error"
                )
            )
            return
        
        # Inicializa score
        self.user_scores[user.id] = 0
        answers = []
        
        # Envia cada pergunta
        for i, question in enumerate(questions):
            # Cria o embed da pergunta
            embed = discord.Embed(
                title=f"{i+1}. {question}",
                description="Digite sua resposta abaixo.",
                color=0x2F3136
            )
            
            await channel.send(embed=embed)
            
            # Espera a resposta
            try:
                response = await self.bot.wait_for(
                    'message',
                    check=lambda m: m.author == user and m.channel == channel,
                    timeout=60.0  # 60 segundos para responder
                )
                
                # Armazena a resposta
                answers.append({
                    'question': question,
                    'answer': response.content,
                    'correct_answer': correct_answers[i]
                })
                
                # Verifica se a resposta está correta (comparação simplificada)
                user_answer = response.content.lower().strip()
                correct = correct_answers[i].lower().strip()
                
                # Verifica se a resposta contém as palavras-chave da resposta correta
                is_correct = all(keyword in user_answer for keyword in correct.split()[:3])
                
                if is_correct:
                    self.user_scores[user.id] += 1
                
            except asyncio.TimeoutError:
                await channel.send(
                    embed=create_embed(
                        "Tempo Esgotado", 
                        "Você demorou muito para responder. Sua whitelist foi cancelada.",
                        color="error"
                    )
                )
                # Se estiver em um canal, agenda a exclusão do canal
                if in_channel:
                    await asyncio.sleep(10)
                    try:
                        await channel.delete()
                    except Exception as e:
                        logger.error(f"Erro ao excluir canal: {e}")
                return
        
        # Calcula o resultado
        passing_score = self.config.get('allowlist', {}).get('passing_score', 7)
        score = self.user_scores[user.id]
        passed = score >= passing_score
        
        # Cria o embed de resultado
        if passed:
            result_embed = discord.Embed(
                title="✅ Whitelist Aprovada!",
                description=(
                    f"Parabéns! Você acertou {score}/{len(questions)} perguntas.\n\n"
                    "Seu acesso ao servidor foi liberado. Divirta-se!"
                ),
                color=0x2ecc71
            )
            
            # Aprova automaticamente a whitelist
            add_to_allowlist(user.id, approved_by=self.bot.user.id, status="approved")
            
            # Gerencia os cargos do usuário
            for guild in self.bot.guilds:
                member = guild.get_member(user.id)
                if member:
                    try:
                        # Remove cargo de turista
                        tourist_role_id = self.config.get('roles', {}).get('tourist')
                        if tourist_role_id:
                            tourist_role = guild.get_role(tourist_role_id)
                            if tourist_role and tourist_role in member.roles:
                                await member.remove_roles(tourist_role)
                        
                        # Adiciona cargo de morador/residente
                        resident_role_id = self.config.get('roles', {}).get('resident')
                        if resident_role_id:
                            resident_role = guild.get_role(resident_role_id)
                            if resident_role:
                                await member.add_roles(resident_role)
                                
                        # Também adiciona o cargo de "allowed" por compatibilidade
                        allowed_role_id = self.config.get('roles', {}).get('allowed')
                        if allowed_role_id and allowed_role_id != resident_role_id:
                            allowed_role = guild.get_role(allowed_role_id)
                            if allowed_role:
                                await member.add_roles(allowed_role)
                    except Exception as e:
                        logger.error(f"Erro ao gerenciar cargos: {e}")
            
            # Notifica canal de aprovados
            try:
                approved_channel_id = self.config.get('channels', {}).get('allowlist_approved')
                if approved_channel_id:
                    approved_channel = self.bot.get_channel(approved_channel_id)
                    if approved_channel:
                        await approved_channel.send(
                            embed=discord.Embed(
                                title="Nova Whitelist Aprovada",
                                description=f"{user.mention} foi aprovado na whitelist com {score}/{len(questions)} acertos!",
                                color=0x2ecc71
                            ).set_thumbnail(url=user.display_avatar.url)
                        )
            except Exception as e:
                logger.error(f"Erro ao enviar notificação de aprovação: {e}")
                
            # Notifica canal de resultados geral
            try:
                results_channel_id = self.config.get('channels', {}).get('allowlist_results')
                if results_channel_id:
                    results_channel = self.bot.get_channel(results_channel_id)
                    if results_channel:
                        await results_channel.send(
                            embed=discord.Embed(
                                title="Resultado de Whitelist",
                                description=f"✅ {user.mention} foi **APROVADO** na whitelist com {score}/{len(questions)} acertos!",
                                color=0x2ecc71,
                                timestamp=datetime.now().astimezone()
                            ).set_thumbnail(url=user.display_avatar.url)
                        )
            except Exception as e:
                logger.error(f"Erro ao enviar resultado: {e}")
            
        else:
            result_embed = discord.Embed(
                title="❌ Whitelist Reprovada",
                description=(
                    f"Você acertou {score}/{len(questions)} perguntas, mas são necessários {passing_score} acertos para aprovação.\n\n"
                    "Você pode tentar novamente mais tarde."
                ),
                color=0xe74c3c
            )
            
            # Registra a reprovação
            add_to_allowlist(user.id, approved_by=None, status="rejected")
            
            # Notifica canal de reprovados
            try:
                rejected_channel_id = self.config.get('channels', {}).get('allowlist_rejected')
                if rejected_channel_id:
                    rejected_channel = self.bot.get_channel(rejected_channel_id)
                    if rejected_channel:
                        await rejected_channel.send(
                            embed=discord.Embed(
                                title="Whitelist Reprovada",
                                description=f"{user.mention} foi reprovado na whitelist com {score}/{len(questions)} acertos.",
                                color=0xe74c3c
                            ).set_thumbnail(url=user.display_avatar.url)
                        )
            except Exception as e:
                logger.error(f"Erro ao enviar notificação de reprovação: {e}")
                
            # Notifica canal de resultados geral
            try:
                results_channel_id = self.config.get('channels', {}).get('allowlist_results')
                if results_channel_id:
                    results_channel = self.bot.get_channel(results_channel_id)
                    if results_channel:
                        await results_channel.send(
                            embed=discord.Embed(
                                title="Resultado de Whitelist",
                                description=f"❌ {user.mention} foi **REPROVADO** na whitelist com {score}/{len(questions)} acertos.",
                                color=0xe74c3c,
                                timestamp=datetime.now().astimezone()
                            ).set_thumbnail(url=user.display_avatar.url)
                        )
            except Exception as e:
                logger.error(f"Erro ao enviar resultado: {e}")
        
        # Envia o resultado
        await channel.send(embed=result_embed)
        
        # Envia mensagem privada ao usuário com o resultado
        try:
            dm_channel = await user.create_dm()
            await dm_channel.send(embed=result_embed)
        except Exception as e:
            logger.error(f"Erro ao enviar resultado por DM: {e}")
        
        # Registra as respostas no banco de dados
        try:
            answers_json = json.dumps(answers)
            update_allowlist_status(
                user.id, 
                "approved" if passed else "rejected",
                self.bot.user.id if passed else None,
                answers_json
            )
        except Exception as e:
            logger.error(f"Erro ao salvar respostas: {e}")
            
        # Se estamos em um canal temporário, agenda sua exclusão
        if in_channel:
            await asyncio.sleep(30)  # Aguarda 30 segundos para o usuário ler o resultado
            try:
                await channel.delete()
            except Exception as e:
                logger.error(f"Erro ao excluir canal: {e}")
            
    async def _notify_approved_channels(self, user, approver):
        """Notifica os canais configurados sobre uma aprovação de whitelist"""
        # Notifica canal de aprovados
        try:
            approved_channel_id = self.config.get('channels', {}).get('allowlist_approved')
            if approved_channel_id:
                approved_channel = self.bot.get_channel(approved_channel_id)
                if approved_channel:
                    embed = discord.Embed(
                        title="Nova Whitelist Aprovada",
                        description=f"{user.mention} foi aprovado na whitelist por {approver.mention}!",
                        color=0x2ecc71,
                        timestamp=datetime.now().astimezone()
                    )
                    
                    # Adiciona avatar do usuário como thumbnail
                    embed.set_thumbnail(url=user.display_avatar.url)
                    
                    await approved_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Erro ao enviar notificação de aprovação: {e}")
            
        # Notifica canal de resultados geral
        try:
            results_channel_id = self.config.get('channels', {}).get('allowlist_results')
            if results_channel_id:
                results_channel = self.bot.get_channel(results_channel_id)
                if results_channel:
                    embed = discord.Embed(
                        title="Resultado de Whitelist",
                        description=f"✅ {user.mention} foi **APROVADO** na whitelist por {approver.mention}!",
                        color=0x2ecc71,
                        timestamp=datetime.now().astimezone()
                    )
                    
                    # Adiciona avatar do usuário como thumbnail
                    embed.set_thumbnail(url=user.display_avatar.url)
                    
                    await results_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Erro ao enviar resultado: {e}")
    
    async def _notify_rejected_channels(self, user, rejecter, reason="Não especificado"):
        """Notifica os canais configurados sobre uma rejeição de whitelist"""
        # Notifica canal de reprovados
        try:
            rejected_channel_id = self.config.get('channels', {}).get('allowlist_rejected')
            if rejected_channel_id:
                rejected_channel = self.bot.get_channel(rejected_channel_id)
                if rejected_channel:
                    embed = discord.Embed(
                        title="Whitelist Reprovada",
                        description=(
                            f"{user.mention} foi reprovado na whitelist por {rejecter.mention}.\n"
                            f"**Motivo:** {reason}"
                        ),
                        color=0xe74c3c,
                        timestamp=datetime.now().astimezone()
                    )
                    
                    # Adiciona avatar do usuário como thumbnail
                    embed.set_thumbnail(url=user.display_avatar.url)
                    
                    await rejected_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Erro ao enviar notificação de reprovação: {e}")
            
        # Notifica canal de resultados geral
        try:
            results_channel_id = self.config.get('channels', {}).get('allowlist_results')
            if results_channel_id:
                results_channel = self.bot.get_channel(results_channel_id)
                if results_channel:
                    embed = discord.Embed(
                        title="Resultado de Whitelist",
                        description=(
                            f"❌ {user.mention} foi **REPROVADO** na whitelist por {rejecter.mention}.\n"
                            f"**Motivo:** {reason}"
                        ),
                        color=0xe74c3c,
                        timestamp=datetime.now().astimezone()
                    )
                    
                    # Adiciona avatar do usuário como thumbnail
                    embed.set_thumbnail(url=user.display_avatar.url)
                    
                    await results_channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Erro ao enviar resultado: {e}")
    
    @allowlist.command(name="dashboard")
    @commands.has_permissions(administrator=True)
    async def dashboard(self, ctx):
        """Painel de controle e status da whitelist"""
        from utils.db import get_allowlist
        
        # Obtém todas as entradas da whitelist
        entries = get_allowlist()
        
        # Separa por status
        approved = [e for e in entries if e['status'] == 'approved']
        pending = [e for e in entries if e['status'] == 'pending']
        rejected = [e for e in entries if e['status'] == 'rejected']
        
        # Cria o embed principal do dashboard
        embed = discord.Embed(
            title="📊 Dashboard de Whitelist",
            description=f"Status atual do sistema de whitelist para o servidor.",
            color=0x3498db
        )
        
        # Adiciona estatísticas
        embed.add_field(
            name="📈 Estatísticas",
            value=(
                f"**Total de entradas:** {len(entries)}\n"
                f"**Aprovados:** {len(approved)}\n"
                f"**Pendentes:** {len(pending)}\n"
                f"**Reprovados:** {len(rejected)}\n"
            ),
            inline=False
        )
        
        # Configurações atuais
        embed.add_field(
            name="⚙️ Configurações",
            value=(
                f"**Pontuação mínima:** {self.config.get('allowlist', {}).get('passing_score', 7)}\n"
                f"**Idade mínima da conta:** {self.config.get('allowlist', {}).get('min_account_age_days', 7)} dias\n"
                f"**Aprovação automática:** {'Ativada' if self.config.get('allowlist', {}).get('auto_approve', False) else 'Desativada'}\n"
            ),
            inline=False
        )
        
        # Aplicações pendentes
        if pending:
            pending_text = ""
            for i, entry in enumerate(pending[:5]):
                user = ctx.guild.get_member(entry['user_id'])
                username = f"{user.mention}" if user else f"ID: {entry['user_id']}"
                pending_text += f"{i+1}. {username}\n"
            
            if len(pending) > 5:
                pending_text += f"*E mais {len(pending) - 5} aplicações pendentes...*"
                
            embed.add_field(
                name="⏳ Aplicações Pendentes",
                value=pending_text,
                inline=False
            )
        
        # Envia o dashboard
        await ctx.send(embed=embed)
        
        # Se houver pendentes, oferece revisão
        if pending:
            # Cria botões para revisar
            view = discord.ui.View(timeout=None)
            
            # Adiciona botão para revisar próximo
            review_button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Revisar Próximo Pendente",
                custom_id="review_next_pending"
            )
            
            # Define callback para o botão
            async def review_callback(interaction):
                if interaction.user.id != ctx.author.id:
                    await interaction.response.send_message("Apenas o administrador que iniciou esta ação pode revisar.", ephemeral=True)
                    return
                
                # Obtém a próxima aplicação pendente
                entry = pending[0]
                user_id = entry['user_id']
                
                # Chama o método de revisão
                await interaction.response.defer()
                await self.review_application(interaction, user_id)
                
            review_button.callback = review_callback
            view.add_item(review_button)
            
            await ctx.send("Deseja revisar as aplicações pendentes?", view=view)
    
    async def review_application(self, interaction, user_id):
        """Revisão interativa de uma aplicação pendente"""
        # Obtém a entrada da whitelist
        entry = check_allowlist(user_id)
        
        if not entry:
            await interaction.followup.send(
                embed=create_embed(
                    "Erro", 
                    f"Nenhuma entrada de whitelist encontrada para o ID {user_id}.",
                    color="error"
                ),
                ephemeral=True
            )
            return
        
        if entry['status'] != 'pending':
            await interaction.followup.send(
                embed=create_embed(
                    "Erro", 
                    f"Esta aplicação não está pendente (status: {entry['status']}).",
                    color="error"
                ),
                ephemeral=True
            )
            return
        
        # Obtém o usuário do servidor
        guild = interaction.guild
        user = guild.get_member(user_id)
        
        if not user:
            user_display = f"ID: {user_id} (não está no servidor)"
        else:
            user_display = f"{user.mention} ({user.name})"
        
        # Analisa as respostas
        try:
            answers = json.loads(entry['answers'])
        except (json.JSONDecodeError, TypeError):
            answers = []
        
        # Cria um embed com as respostas (como na interface da imagem)
        review_embed = discord.Embed(
            title=f"Revisão de Whitelist - {user_display.split()[0]}",
            description=f"Analise as respostas abaixo e aprove ou rejeite a aplicação.",
            color=0x2F3136
        )
        
        if user:
            review_embed.set_thumbnail(url=user.display_avatar.url)
        
        # Adiciona cada pergunta e resposta como um campo
        for i, qa in enumerate(answers):
            question = qa.get('question', 'Pergunta desconhecida')
            answer = qa.get('answer', 'Sem resposta')
            
            # Verifica se a resposta está correta
            correct_answer = qa.get('correct_answer', '')
            user_answer = answer.lower().strip()
            correct = correct_answer.lower().strip()
            
            # Verifica se contém palavras-chave da resposta correta
            is_correct = all(keyword in user_answer for keyword in correct.split()[:3])
            
            # Formata o campo com emoji de correto/incorreto
            field_name = f"{i+1}. {question}"
            field_value = f"{'✅' if is_correct else '❌'} {answer}"
            
            review_embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
            )
        
        # Adiciona um rodapé com a data da aplicação
        if entry.get('created_at'):
            review_embed.set_footer(text=f"Aplicação enviada em: {entry['created_at']}")
        
        # Cria os botões de aprovação/rejeição
        view = WhitelistReviewButtons(user_id, self.bot)
        
        # Envia o embed de revisão com os botões
        await interaction.followup.send(embed=review_embed, view=view)
    
    @allowlist.command(name="configure")
    @commands.has_permissions(administrator=True)
    async def configure_allowlist(self, ctx, setting=None, value=None):
        """Configura parâmetros do sistema de whitelist
        
        Configurações disponíveis:
        - passing_score: Pontuação mínima para aprovação (1-10)
        - min_account_age: Idade mínima da conta em dias
        - auto_approve: Liga/desliga aprovação automática (true/false)
        """
        if not setting:
            # Exibe configurações atuais
            embed = discord.Embed(
                title="⚙️ Configurações de Whitelist",
                description="Configurações atuais do sistema de whitelist.",
                color=0x3498db
            )
            
            embed.add_field(
                name="Comandos de Configuração",
                value=(
                    f"`!allowlist configure passing_score <valor>` - Define pontuação mínima (1-10)\n"
                    f"`!allowlist configure min_account_age <dias>` - Define idade mínima da conta\n"
                    f"`!allowlist configure auto_approve <true/false>` - Ativa/desativa aprovação automática\n"
                ),
                inline=False
            )
            
            embed.add_field(
                name="Valores Atuais",
                value=(
                    f"**Pontuação mínima:** {self.config.get('allowlist', {}).get('passing_score', 7)}\n"
                    f"**Idade mínima da conta:** {self.config.get('allowlist', {}).get('min_account_age_days', 7)} dias\n"
                    f"**Aprovação automática:** {'Ativada' if self.config.get('allowlist', {}).get('auto_approve', False) else 'Desativada'}\n"
                ),
                inline=False
            )
            
            await ctx.send(embed=embed)
            return
        
        # Verifica se o valor foi informado
        if value is None:
            await ctx.send(
                embed=create_embed(
                    "Erro", 
                    f"Você precisa informar um valor para a configuração '{setting}'.",
                    color="error"
                )
            )
            return
        
        # Atualiza a configuração
        config = load_config()
        
        if setting == "passing_score":
            try:
                score = int(value)
                if score < 1 or score > 10:
                    await ctx.send(
                        embed=create_embed(
                            "Erro", 
                            "A pontuação mínima deve ser um número entre 1 e 10.",
                            color="error"
                        )
                    )
                    return
                
                # Atualiza a configuração
                if 'allowlist' not in config:
                    config['allowlist'] = {}
                config['allowlist']['passing_score'] = score
                
                # Salva a configuração
                with open('config.json', 'w') as f:
                    json.dump(config, f, indent=4)
                
                # Recarrega a configuração
                self.config = load_config()
                
                await ctx.send(
                    embed=create_embed(
                        "Configuração Atualizada", 
                        f"A pontuação mínima para aprovação foi definida para {score}.",
                        color="success"
                    )
                )
            except ValueError:
                await ctx.send(
                    embed=create_embed(
                        "Erro", 
                        "O valor deve ser um número inteiro.",
                        color="error"
                    )
                )
                
        elif setting == "min_account_age":
            try:
                days = int(value)
                if days < 0:
                    await ctx.send(
                        embed=create_embed(
                            "Erro", 
                            "A idade mínima da conta deve ser um número positivo.",
                            color="error"
                        )
                    )
                    return
                
                # Atualiza a configuração
                if 'allowlist' not in config:
                    config['allowlist'] = {}
                config['allowlist']['min_account_age_days'] = days
                
                # Salva a configuração
                with open('config.json', 'w') as f:
                    json.dump(config, f, indent=4)
                
                # Recarrega a configuração
                self.config = load_config()
                
                await ctx.send(
                    embed=create_embed(
                        "Configuração Atualizada", 
                        f"A idade mínima da conta foi definida para {days} dias.",
                        color="success"
                    )
                )
            except ValueError:
                await ctx.send(
                    embed=create_embed(
                        "Erro", 
                        "O valor deve ser um número inteiro.",
                        color="error"
                    )
                )
                
        elif setting == "auto_approve":
            if value.lower() in ["true", "yes", "sim", "1", "on"]:
                auto_approve = True
            elif value.lower() in ["false", "no", "não", "nao", "0", "off"]:
                auto_approve = False
            else:
                await ctx.send(
                    embed=create_embed(
                        "Erro", 
                        "O valor deve ser 'true' ou 'false'.",
                        color="error"
                    )
                )
                return
            
            # Atualiza a configuração
            if 'allowlist' not in config:
                config['allowlist'] = {}
            config['allowlist']['auto_approve'] = auto_approve
            
            # Salva a configuração
            with open('config.json', 'w') as f:
                json.dump(config, f, indent=4)
            
            # Recarrega a configuração
            self.config = load_config()
            
            await ctx.send(
                embed=create_embed(
                    "Configuração Atualizada", 
                    f"A aprovação automática foi {'ativada' if auto_approve else 'desativada'}.",
                    color="success"
                )
            )
        else:
            await ctx.send(
                embed=create_embed(
                    "Erro", 
                    f"Configuração '{setting}' não reconhecida. Configurações disponíveis: passing_score, min_account_age, auto_approve.",
                    color="error"
                )
            )
    
    @allowlist.command(name="list")
    @commands.check(can_use_allowlist_commands)
    async def list_allowlist(self, ctx):
        """List all users on the allowlist"""
        from utils.db import get_allowlist
        
        entries = get_allowlist()
        
        if not entries:
            await ctx.send(
                embed=create_embed(
                    "Allowlist", 
                    "There are no users on the allowlist.",
                    color="info"
                )
            )
            return
        
        # Filter to show only approved entries
        approved_entries = [e for e in entries if e['status'] == 'approved']
        pending_entries = [e for e in entries if e['status'] == 'pending']
        
        # Create paginated embeds for approved users
        if approved_entries:
            approved_text = "**Approved Users:**\n"
            for entry in approved_entries[:20]:  # Limit to 20 users per page
                user = ctx.guild.get_member(entry['user_id'])
                username = user.mention if user else f"Unknown User ({entry['user_id']})"
                approved_text += f"• {username}\n"
            
            if len(approved_entries) > 20:
                approved_text += f"\n*And {len(approved_entries) - 20} more users...*"
        else:
            approved_text = "No approved users."
        
        # Show count of pending applications
        pending_text = f"There are **{len(pending_entries)}** pending applications."
        
        await ctx.send(
            embed=create_embed(
                "Allowlist Status", 
                f"{approved_text}\n\n{pending_text}",
                color="info"
            )
        )
    
    @allowlist.command(name="review")
    @commands.check(can_use_allowlist_commands)
    async def review(self, ctx, user_id: int):
        """Review a pending allowlist application"""
        # Get allowlist entry
        try:
            entry = check_allowlist(user_id)
            
            if not entry:
                await ctx.send(
                    embed=create_embed(
                        "Erro", 
                        f"Nenhuma entrada de whitelist encontrada para o ID {user_id}.",
                        color="error"
                    )
                )
                return
            
            if entry['status'] != 'pending':
                await ctx.send(
                    embed=create_embed(
                        "Erro", 
                        f"Esta aplicação não está pendente (status: {entry['status']}).",
                        color="error"
                    )
                )
                return
            
            # Get the user from the guild
            user = ctx.guild.get_member(user_id)
            if not user:
                user_display = f"ID: {user_id} (não está no servidor)"
            else:
                user_display = f"{user.mention} ({user.name})"
            
            # Parse the answers
            try:
                answers = json.loads(entry['answers'])
            except (json.JSONDecodeError, TypeError):
                answers = []
            
            # Create an embed with the answers (like the image interface)
            review_embed = discord.Embed(
                title=f"Revisão de Whitelist - {user_display.split()[0]}",
                description=f"Analise as respostas abaixo e aprove ou rejeite a aplicação.",
                color=0x2F3136
            )
            
            if user:
                review_embed.set_thumbnail(url=user.display_avatar.url)
            
            # Add each question and answer as a field
            correct_answers = self.config.get('allowlist', {}).get('correct_answers', [])
            
            for i, qa in enumerate(answers):
                question = qa.get('question', 'Pergunta desconhecida')
                answer = qa.get('answer', 'Sem resposta')
                
                # Check if the answer is correct if possible
                correct_answer = None
                if i < len(correct_answers):
                    correct_answer = correct_answers[i]
                
                if correct_answer:
                    user_answer = answer.lower().strip()
                    correct = correct_answer.lower().strip()
                    
                    # Check if it contains keywords of the correct answer
                    is_correct = all(keyword in user_answer for keyword in correct.split()[:3])
                    
                    # Format field with correct/incorrect emoji
                    field_name = f"{i+1}. {question}"
                    field_value = f"{'✅' if is_correct else '❌'} {answer}"
                else:
                    field_name = f"{i+1}. {question}"
                    field_value = answer
                
                review_embed.add_field(
                    name=field_name,
                    value=field_value,
                    inline=False
                )
            
            # Add footer with application date
            if entry.get('created_at'):
                review_embed.set_footer(text=f"Aplicação enviada em: {entry['created_at']}")
            
            # Create approval/rejection buttons
            view = WhitelistReviewButtons(user_id, self.bot)
            
            # Send the review embed with buttons
            await ctx.send(embed=review_embed, view=view)
                
        except Exception as e:
            logger.error(f"Erro ao revisar aplicação: {e}")
            await ctx.send(
                embed=create_embed(
                    "Erro", 
                    f"Ocorreu um erro: {str(e)}",
                    color="error"
                )
            )
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Check allowlist status when a member joins"""
        # Skip if the user is a bot
        if member.bot:
            return
        
        # Check if auto-role is enabled
        entry = check_allowlist(member.id)
        
        if entry and entry['status'] == 'approved':
            try:
                # Remove cargo de turista
                tourist_role_id = self.config.get('roles', {}).get('tourist')
                if tourist_role_id:
                    tourist_role = member.guild.get_role(tourist_role_id)
                    if tourist_role and tourist_role in member.roles:
                        await member.remove_roles(tourist_role)
                        logger.info(f"Removido cargo de turista de {member.id} ao entrar no servidor")
                
                # Adiciona cargo de morador/residente
                resident_role_id = self.config.get('roles', {}).get('resident')
                if resident_role_id:
                    resident_role = member.guild.get_role(resident_role_id)
                    if resident_role:
                        await member.add_roles(resident_role)
                        logger.info(f"Adicionado cargo de morador para {member.id} ao entrar no servidor")
                
                # Também adiciona o cargo de "allowed" por compatibilidade
                allowed_role_id = self.config.get('roles', {}).get('allowed')
                if allowed_role_id and allowed_role_id != resident_role_id:
                    allowed_role = member.guild.get_role(allowed_role_id)
                    if allowed_role:
                        await member.add_roles(allowed_role)
                        logger.info(f"Adicionado cargo de permitido para {member.id} ao entrar no servidor")
                
                # Envia mensagem de boas-vindas por DM
                server_name = self.config.get('server_name', 'Servidor')
                try:
                    await member.send(
                        embed=create_embed(
                            f"Bem-vindo(a) ao {server_name}!",
                            f"Sua whitelist foi aprovada e você tem agora acesso completo ao servidor. Aproveite sua experiência!",
                            color="success"
                        )
                    )
                except discord.Forbidden:
                    # Não pode enviar DM para o usuário
                    logger.info(f"Não foi possível enviar mensagem privada de boas-vindas para {member.id}")
                
            except discord.errors.Forbidden:
                logger.error(f"Sem permissão para gerenciar cargos para {member.id}")
            except Exception as e:
                logger.error(f"Erro ao gerenciar cargos para {member.id}: {e}")

async def setup(bot):
    await bot.add_cog(Allowlist(bot))
