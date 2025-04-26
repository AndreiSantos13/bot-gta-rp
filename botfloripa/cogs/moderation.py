import discord
from discord.ext import commands
import asyncio
import logging
from datetime import datetime, timedelta
import json

from utils.db import (
    add_warning, get_warnings, clear_warnings, 
    add_ban, remove_ban, get_active_ban, get_all_bans
)
from utils.helpers import (
    create_embed, load_config, can_use_moderation_commands,
    parse_time, format_time_difference
)

logger = logging.getLogger("bot.moderation")

class Moderation(commands.Cog):
    """Handles moderation commands for server management"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
        self.ban_check_task = self.bot.loop.create_task(self.check_temp_bans())
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.ban_check_task.cancel()
    
    async def check_temp_bans(self):
        """Background task to check for expired temporary bans"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                # Get all active bans
                bans = get_all_bans()
                now = datetime.now()
                
                for ban in bans:
                    # Skip if not a temp ban or no expiration
                    if not ban['expires_at']:
                        continue
                    
                    # Parse the expiration date
                    try:
                        expires_at = datetime.fromisoformat(ban['expires_at'])
                    except (ValueError, TypeError):
                        continue
                    
                    # Check if ban has expired
                    if now >= expires_at:
                        # Mark as inactive in database
                        remove_ban(ban['user_id'])
                        
                        # Try to unban on Discord
                        for guild in self.bot.guilds:
                            try:
                                # Get ban info from Discord
                                banned_user = await guild.fetch_ban(discord.Object(id=ban['user_id']))
                                if banned_user:
                                    await guild.unban(
                                        discord.Object(id=ban['user_id']), 
                                        reason="Temporary ban expired"
                                    )
                                    logger.info(f"Unbanned user {ban['user_id']} (temp ban expired)")
                                    
                                    # Try to log the unban
                                    log_channel_id = self.config.get('channels', {}).get('logs')
                                    if log_channel_id:
                                        log_channel = guild.get_channel(log_channel_id)
                                        if log_channel:
                                            await log_channel.send(
                                                embed=create_embed(
                                                    "Temporary Ban Expired",
                                                    f"User <@{ban['user_id']}> has been automatically unbanned.",
                                                    color="info"
                                                )
                                            )
                            except (discord.errors.NotFound, discord.errors.Forbidden):
                                # User was not banned or no permission
                                pass
                            except Exception as e:
                                logger.error(f"Error unbanning user {ban['user_id']}: {e}")
            
            except Exception as e:
                logger.error(f"Error in temp ban check task: {e}")
            
            # Check every 5 minutes
            await asyncio.sleep(300)
    
    @commands.command(name="warn")
    @commands.check(can_use_moderation_commands)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Warn a user for breaking the rules"""
        # Don't allow warning bots or staff
        if member.bot:
            await ctx.send("You cannot warn bots.")
            return
        
        if can_use_moderation_commands(member):
            await ctx.send("You cannot warn other staff members.")
            return
        
        # Add warning to database
        try:
            warning_id = add_warning(member.id, ctx.author.id, reason)
            
            if warning_id:
                # Get count of active warnings
                warnings = get_warnings(member.id, active_only=True)
                warning_count = len(warnings)
                
                # Send confirmation
                await ctx.send(
                    embed=create_embed(
                        "Warning Issued",
                        f"{member.mention} has been warned by {ctx.author.mention}.",
                        color="warning",
                        fields=[
                            {"name": "Reason", "value": reason, "inline": False},
                            {"name": "Warning Count", "value": str(warning_count), "inline": True},
                            {"name": "Warning ID", "value": str(warning_id), "inline": True}
                        ]
                    )
                )
                
                # DM the user
                try:
                    await member.send(
                        embed=create_embed(
                            "Warning Received",
                            f"You have received a warning in **{ctx.guild.name}**.",
                            color="warning",
                            fields=[
                                {"name": "Reason", "value": reason, "inline": False},
                                {"name": "Warning Count", "value": str(warning_count), "inline": True},
                                {"name": "Moderator", "value": str(ctx.author), "inline": True}
                            ]
                        )
                    )
                except discord.errors.Forbidden:
                    # User has DMs closed
                    await ctx.send("Note: Unable to DM user about this warning.")
                
                # Log the warning
                log_channel_id = self.config.get('channels', {}).get('logs')
                if log_channel_id:
                    log_channel = ctx.guild.get_channel(log_channel_id)
                    if log_channel:
                        await log_channel.send(
                            embed=create_embed(
                                "Warning Issued",
                                f"{member.mention} has been warned by {ctx.author.mention}.",
                                color="warning",
                                fields=[
                                    {"name": "Reason", "value": reason, "inline": False},
                                    {"name": "Warning Count", "value": str(warning_count), "inline": True},
                                    {"name": "Warning ID", "value": str(warning_id), "inline": True}
                                ]
                            )
                        )
            else:
                await ctx.send("Failed to add warning. Check the logs for details.")
                
        except Exception as e:
            logger.error(f"Error issuing warning: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="warnings", aliases=["warns"])
    @commands.check(can_use_moderation_commands)
    async def warnings(self, ctx, member: discord.Member):
        """Show warnings for a user"""
        # Get warnings from database
        warnings = get_warnings(member.id, active_only=False)
        
        if not warnings:
            await ctx.send(
                embed=create_embed(
                    "Warnings",
                    f"{member.mention} has no warnings.",
                    color="success"
                )
            )
            return
        
        # Count active warnings
        active_warnings = [w for w in warnings if w['active']]
        
        # Create embed with warning info
        embed = create_embed(
            "Warnings",
            f"{member.mention} has {len(active_warnings)} active warning(s) out of {len(warnings)} total.",
            color="warning"
        )
        
        # Add fields for each warning (up to 10)
        displayed_warnings = warnings[:10]
        
        for i, warning in enumerate(displayed_warnings):
            # Get moderator info
            mod_info = f"<@{warning['moderator_id']}>"
            
            # Format timestamp
            timestamp = "Unknown"
            if warning['timestamp']:
                try:
                    timestamp = datetime.fromisoformat(warning['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    timestamp = warning['timestamp']
            
            # Format status
            status = "Active" if warning['active'] else "Removed"
            
            embed.add_field(
                name=f"Warning #{i+1} ({status})",
                value=f"**Reason:** {warning['reason']}\n**By:** {mod_info}\n**Date:** {timestamp}",
                inline=False
            )
        
        # Add note if there are more warnings
        if len(warnings) > 10:
            embed.add_field(
                name="Note",
                value=f"Showing 10/{len(warnings)} warnings. Use `!warnlog {member.id}` for full details.",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="clearwarnings", aliases=["clearwarns"])
    @commands.check(can_use_moderation_commands)
    async def clearwarnings(self, ctx, member: discord.Member):
        """Clear all warnings for a user"""
        # Check if user has any warnings
        warnings = get_warnings(member.id, active_only=True)
        
        if not warnings:
            await ctx.send(
                embed=create_embed(
                    "Warnings",
                    f"{member.mention} has no active warnings to clear.",
                    color="info"
                )
            )
            return
        
        # Clear warnings
        try:
            cleared_count = clear_warnings(member.id, ctx.author.id)
            
            if cleared_count > 0:
                await ctx.send(
                    embed=create_embed(
                        "Warnings Cleared",
                        f"Cleared {cleared_count} warning(s) for {member.mention}.",
                        color="success"
                    )
                )
                
                # DM the user
                try:
                    await member.send(
                        embed=create_embed(
                            "Warnings Cleared",
                            f"Your warnings in **{ctx.guild.name}** have been cleared by {ctx.author.mention}.",
                            color="success"
                        )
                    )
                except discord.errors.Forbidden:
                    # User has DMs closed
                    pass
                
                # Log the action
                log_channel_id = self.config.get('channels', {}).get('logs')
                if log_channel_id:
                    log_channel = ctx.guild.get_channel(log_channel_id)
                    if log_channel:
                        await log_channel.send(
                            embed=create_embed(
                                "Warnings Cleared",
                                f"{cleared_count} warning(s) for {member.mention} have been cleared by {ctx.author.mention}.",
                                color="info"
                            )
                        )
            else:
                await ctx.send("Failed to clear warnings. Check the logs for details.")
                
        except Exception as e:
            logger.error(f"Error clearing warnings: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="ban")
    @commands.check(can_use_moderation_commands)
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, user: discord.User, time_str=None, *, reason="No reason provided"):
        """Ban a user from the server (permanently or temporarily)"""
        # Check if the user is already banned
        try:
            await ctx.guild.fetch_ban(user)
            await ctx.send(
                embed=create_embed(
                    "Error",
                    f"{user.mention} is already banned from this server.",
                    color="error"
                )
            )
            return
        except discord.errors.NotFound:
            # User is not banned, we can proceed
            pass
        
        # Don't allow banning staff (if user is in the guild)
        member = ctx.guild.get_member(user.id)
        if member and can_use_moderation_commands(member):
            await ctx.send("You cannot ban other staff members.")
            return
        
        # Parse temporary ban duration
        expires_at = None
        if time_str:
            duration = parse_time(time_str)
            if duration:
                now = datetime.now().astimezone()  # Converter para aware datetime
                expires_at = (now + duration).isoformat()
                time_display = format_time_difference(now + duration)
            else:
                # Couldn't parse the time, treat it as part of the reason
                reason = f"{time_str} {reason}".strip()
        
        ban_type = "Temporary Ban" if expires_at else "Permanent Ban"
        
        # Ban the user
        try:
            # Add ban to database first
            ban_id = add_ban(user.id, ctx.author.id, reason, expires_at)
            
            if not ban_id:
                await ctx.send("Failed to record ban in database. Aborting.")
                return
            
            # Execute the ban on Discord
            await ctx.guild.ban(user, reason=reason, delete_message_days=1)
            
            # Prepare confirmation message
            fields = [
                {"name": "User", "value": f"{user.mention} ({user.id})", "inline": True},
                {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                {"name": "Reason", "value": reason, "inline": False}
            ]
            
            if expires_at:
                fields.append({"name": "Duration", "value": time_display, "inline": True})
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    ban_type,
                    f"{user.mention} has been banned from the server.",
                    color="error",
                    fields=fields
                )
            )
            
            # Log the ban
            log_channel_id = self.config.get('channels', {}).get('logs')
            if log_channel_id:
                log_channel = ctx.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(
                        embed=create_embed(
                            ban_type,
                            f"{user.mention} has been banned by {ctx.author.mention}.",
                            color="error",
                            fields=fields
                        )
                    )
        
        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to ban this user.")
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="unban")
    @commands.check(can_use_moderation_commands)
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason="No reason provided"):
        """Unban a user by ID"""
        try:
            # Check if user is banned on Discord
            try:
                ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
                user = ban_entry.user
            except discord.errors.NotFound:
                await ctx.send(
                    embed=create_embed(
                        "Error",
                        f"User with ID {user_id} is not banned.",
                        color="error"
                    )
                )
                return
            
            # Update database
            success = remove_ban(user_id)
            
            # Unban on Discord
            await ctx.guild.unban(user, reason=reason)
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "User Unbanned",
                    f"{user.mention} has been unbanned by {ctx.author.mention}.",
                    color="success",
                    fields=[
                        {"name": "User", "value": f"{user.mention} ({user.id})", "inline": True},
                        {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                        {"name": "Reason", "value": reason, "inline": False}
                    ]
                )
            )
            
            # Log the unban
            log_channel_id = self.config.get('channels', {}).get('logs')
            if log_channel_id:
                log_channel = ctx.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(
                        embed=create_embed(
                            "User Unbanned",
                            f"{user.mention} has been unbanned by {ctx.author.mention}.",
                            color="success",
                            fields=[
                                {"name": "User", "value": f"{user.mention} ({user.id})", "inline": True},
                                {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                                {"name": "Reason", "value": reason, "inline": False}
                            ]
                        )
                    )
                    
        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to unban users.")
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="kick")
    @commands.check(can_use_moderation_commands)
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Kick a user from the server"""
        # Don't allow kicking bots or staff
        if member.bot:
            await ctx.send("You cannot kick bots.")
            return
        
        if can_use_moderation_commands(member):
            await ctx.send("You cannot kick other staff members.")
            return
        
        try:
            # Try to DM the user before kicking
            try:
                await member.send(
                    embed=create_embed(
                        "Kicked",
                        f"You have been kicked from **{ctx.guild.name}**.",
                        color="error",
                        fields=[
                            {"name": "Reason", "value": reason, "inline": False},
                            {"name": "Moderator", "value": str(ctx.author), "inline": True}
                        ]
                    )
                )
            except discord.errors.Forbidden:
                # User has DMs closed
                pass
            
            # Kick the member
            await member.kick(reason=reason)
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "User Kicked",
                    f"{member.mention} has been kicked by {ctx.author.mention}.",
                    color="warning",
                    fields=[
                        {"name": "User", "value": f"{member.mention} ({member.id})", "inline": True},
                        {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                        {"name": "Reason", "value": reason, "inline": False}
                    ]
                )
            )
            
            # Log the kick
            log_channel_id = self.config.get('channels', {}).get('logs')
            if log_channel_id:
                log_channel = ctx.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(
                        embed=create_embed(
                            "User Kicked",
                            f"{member.mention} has been kicked by {ctx.author.mention}.",
                            color="warning",
                            fields=[
                                {"name": "User", "value": f"{member.mention} ({member.id})", "inline": True},
                                {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                                {"name": "Reason", "value": reason, "inline": False}
                            ]
                        )
                    )
                    
        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to kick this user.")
        except Exception as e:
            logger.error(f"Error kicking user: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="mute")
    @commands.check(can_use_moderation_commands)
    @commands.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, time_str=None, *, reason="No reason provided"):
        """Timeout (mute) a user for a specific duration"""
        # Don't allow muting bots or staff
        if member.bot:
            await ctx.send("You cannot mute bots.")
            return
        
        if can_use_moderation_commands(member):
            await ctx.send("You cannot mute other staff members.")
            return
        
        # Parse duration - default to 10 minutes if not specified
        duration = parse_time(time_str) if time_str else timedelta(minutes=10)
        
        if not duration:
            # Couldn't parse the time, treat it as part of the reason
            reason = f"{time_str} {reason}".strip()
            duration = timedelta(minutes=10)
        
        # Make sure duration is within Discord's limits (max 28 days)
        max_duration = timedelta(days=28)
        if duration > max_duration:
            duration = max_duration
            await ctx.send("Note: Maximum timeout duration is 28 days. Setting to maximum.")
        
        # Calculate end time for display
        now = datetime.now().astimezone()  # Converter para aware datetime
        until = now + duration
        time_display = format_time_difference(until)
        
        try:
            # Apply timeout
            await member.timeout(duration, reason=reason)
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "User Timed Out",
                    f"{member.mention} has been timed out by {ctx.author.mention}.",
                    color="warning",
                    fields=[
                        {"name": "User", "value": f"{member.mention} ({member.id})", "inline": True},
                        {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                        {"name": "Duration", "value": time_display, "inline": True},
                        {"name": "Reason", "value": reason, "inline": False}
                    ]
                )
            )
            
            # DM the user
            try:
                await member.send(
                    embed=create_embed(
                        "Timed Out",
                        f"You have been timed out in **{ctx.guild.name}**.",
                        color="warning",
                        fields=[
                            {"name": "Duration", "value": time_display, "inline": True},
                            {"name": "Reason", "value": reason, "inline": False},
                            {"name": "Moderator", "value": str(ctx.author), "inline": True}
                        ]
                    )
                )
            except discord.errors.Forbidden:
                # User has DMs closed
                pass
            
            # Log the mute
            log_channel_id = self.config.get('channels', {}).get('logs')
            if log_channel_id:
                log_channel = ctx.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(
                        embed=create_embed(
                            "User Timed Out",
                            f"{member.mention} has been timed out by {ctx.author.mention}.",
                            color="warning",
                            fields=[
                                {"name": "User", "value": f"{member.mention} ({member.id})", "inline": True},
                                {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                                {"name": "Duration", "value": time_display, "inline": True},
                                {"name": "Reason", "value": reason, "inline": False}
                            ]
                        )
                    )
                    
        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to time out this user.")
        except Exception as e:
            logger.error(f"Error timing out user: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="unmute")
    @commands.check(can_use_moderation_commands)
    @commands.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason="No reason provided"):
        """Remove timeout (unmute) from a user"""
        try:
            # Check if user is actually timed out
            if not member.is_timed_out():
                await ctx.send(f"{member.mention} is not currently timed out.")
                return
            
            # Remove timeout
            await member.timeout(None, reason=reason)
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "User Unmuted",
                    f"{member.mention} has been unmuted by {ctx.author.mention}.",
                    color="success",
                    fields=[
                        {"name": "User", "value": f"{member.mention} ({member.id})", "inline": True},
                        {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                        {"name": "Reason", "value": reason, "inline": False}
                    ]
                )
            )
            
            # DM the user
            try:
                await member.send(
                    embed=create_embed(
                        "Timeout Removed",
                        f"Your timeout in **{ctx.guild.name}** has been removed.",
                        color="success",
                        fields=[
                            {"name": "Reason", "value": reason, "inline": False},
                            {"name": "Moderator", "value": str(ctx.author), "inline": True}
                        ]
                    )
                )
            except discord.errors.Forbidden:
                # User has DMs closed
                pass
            
            # Log the unmute
            log_channel_id = self.config.get('channels', {}).get('logs')
            if log_channel_id:
                log_channel = ctx.guild.get_channel(log_channel_id)
                if log_channel:
                    await log_channel.send(
                        embed=create_embed(
                            "User Unmuted",
                            f"{member.mention} has been unmuted by {ctx.author.mention}.",
                            color="success",
                            fields=[
                                {"name": "User", "value": f"{member.mention} ({member.id})", "inline": True},
                                {"name": "Moderator", "value": ctx.author.mention, "inline": True},
                                {"name": "Reason", "value": reason, "inline": False}
                            ]
                        )
                    )
                    
        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to remove this user's timeout.")
        except Exception as e:
            logger.error(f"Error removing timeout: {e}")
            await ctx.send(f"An error occurred: {str(e)}")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
