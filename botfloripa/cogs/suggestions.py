import discord
from discord.ext import commands
import asyncio
import logging
from datetime import datetime

from utils.db import (
    add_suggestion, update_suggestion_status, 
    get_suggestion, get_suggestion_by_message
)
from utils.helpers import (
    create_embed, load_config, can_use_suggestion_management
)

logger = logging.getLogger("bot.suggestions")

class Suggestions(commands.Cog):
    """Handles the suggestion system for the server"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
    
    @commands.command(name="suggest")
    async def suggest(self, ctx, *, suggestion=None):
        """Submit a suggestion for the server"""
        if not suggestion:
            await ctx.send("Please provide a suggestion. Usage: `!suggest <your suggestion>`")
            return
        
        # Get the suggestion channel from config
        suggestion_channel_id = self.config.get('channels', {}).get('suggestions')
        
        if not suggestion_channel_id:
            # If no channel configured, check if there are channel mentions
            if ctx.message.channel_mentions:
                channel = ctx.message.channel_mentions[0]
                # Remove the channel mention from the suggestion
                suggestion = suggestion.replace(f"<#{channel.id}>", "", 1).strip()
            else:
                await ctx.send(
                    "No suggestion channel is configured. Please contact an administrator to set up the suggestion system."
                )
                return
        else:
            channel = ctx.guild.get_channel(suggestion_channel_id)
        
        if not channel:
            await ctx.send(
                "Suggestion channel not found or not accessible. Please contact an administrator."
            )
            return
        
        try:
            # Create suggestion embed
            embed = create_embed(
                "New Suggestion",
                suggestion,
                color="info"
            )
            
            # Add author info
            embed.set_author(
                name=f"Suggested by {ctx.author.display_name}",
                icon_url=ctx.author.display_avatar.url
            )
            
            # Add timestamp
            embed.timestamp = datetime.now().astimezone()
            
            # Send to suggestion channel
            suggestion_msg = await channel.send(embed=embed)
            
            # Add voting reactions
            await suggestion_msg.add_reaction("👍")
            await suggestion_msg.add_reaction("👎")
            
            # Save suggestion to database
            suggestion_id = add_suggestion(ctx.author.id, suggestion, suggestion_msg.id, channel.id)
            
            if suggestion_id:
                # Add suggestion ID to the embed
                embed.set_footer(text=f"Suggestion ID: {suggestion_id}")
                await suggestion_msg.edit(embed=embed)
                
                # Send confirmation to user
                await ctx.send(
                    embed=create_embed(
                        "Suggestion Submitted",
                        f"Your suggestion has been submitted! You can view it in {channel.mention}.",
                        color="success"
                    )
                )
            else:
                logger.error("Failed to add suggestion to database")
                # Still confirm to the user since the message was sent
                await ctx.send(
                    embed=create_embed(
                        "Suggestion Submitted",
                        f"Your suggestion has been submitted! You can view it in {channel.mention}.",
                        color="success"
                    )
                )
        
        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to send messages or add reactions in the suggestion channel.")
        except Exception as e:
            logger.error(f"Error submitting suggestion: {e}")
            await ctx.send(f"An error occurred while submitting your suggestion: {str(e)}")
    
    @commands.command(name="approve")
    @commands.check(can_use_suggestion_management)
    async def approve_suggestion(self, ctx, suggestion_id: int, *, comment=None):
        """Approve a suggestion with an optional comment"""
        suggestion = get_suggestion(suggestion_id)
        
        if not suggestion:
            await ctx.send(f"Suggestion with ID {suggestion_id} not found.")
            return
        
        try:
            # Get the message
            channel = self.bot.get_channel(suggestion['channel_id'])
            if not channel:
                await ctx.send("Suggestion channel not found or not accessible.")
                return
            
            try:
                message = await channel.fetch_message(suggestion['message_id'])
            except (discord.errors.NotFound, discord.errors.Forbidden):
                await ctx.send("Suggestion message not found or not accessible.")
                return
            
            # Update the embed
            embed = message.embeds[0] if message.embeds else discord.Embed(
                title="Suggestion",
                description=suggestion['content']
            )
            
            # Change color to green
            embed.color = discord.Color.green()
            
            # Add status field
            status_text = "✅ Approved"
            if comment:
                status_text += f"\n\n**Comment:** {comment}"
            
            # Find if there's already a field for status or add a new one
            status_field_found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Status":
                    embed.set_field_at(i, name="Status", value=status_text, inline=False)
                    status_field_found = True
                    break
            
            if not status_field_found:
                embed.add_field(name="Status", value=status_text, inline=False)
            
            # Update the message
            await message.edit(embed=embed)
            
            # Update in database
            update_suggestion_status(suggestion_id, "approved")
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "Suggestion Approved",
                    f"Suggestion #{suggestion_id} has been approved.",
                    color="success"
                )
            )
            
            # Try to notify the suggester
            try:
                suggester = ctx.guild.get_member(suggestion['user_id'])
                if suggester:
                    await suggester.send(
                        embed=create_embed(
                            "Suggestion Approved",
                            f"Your suggestion has been approved by {ctx.author.mention}!",
                            color="success",
                            fields=[
                                {"name": "Your Suggestion", "value": suggestion['content'], "inline": False}
                            ] + ([{"name": "Comment", "value": comment, "inline": False}] if comment else [])
                        )
                    )
            except discord.errors.Forbidden:
                # Can't DM user
                pass
            except Exception as e:
                logger.error(f"Error notifying suggestion author: {e}")
            
        except Exception as e:
            logger.error(f"Error approving suggestion: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="reject")
    @commands.check(can_use_suggestion_management)
    async def reject_suggestion(self, ctx, suggestion_id: int, *, reason=None):
        """Reject a suggestion with an optional reason"""
        suggestion = get_suggestion(suggestion_id)
        
        if not suggestion:
            await ctx.send(f"Suggestion with ID {suggestion_id} not found.")
            return
        
        try:
            # Get the message
            channel = self.bot.get_channel(suggestion['channel_id'])
            if not channel:
                await ctx.send("Suggestion channel not found or not accessible.")
                return
            
            try:
                message = await channel.fetch_message(suggestion['message_id'])
            except (discord.errors.NotFound, discord.errors.Forbidden):
                await ctx.send("Suggestion message not found or not accessible.")
                return
            
            # Update the embed
            embed = message.embeds[0] if message.embeds else discord.Embed(
                title="Suggestion",
                description=suggestion['content']
            )
            
            # Change color to red
            embed.color = discord.Color.red()
            
            # Add status field
            status_text = "❌ Rejected"
            if reason:
                status_text += f"\n\n**Reason:** {reason}"
            
            # Find if there's already a field for status or add a new one
            status_field_found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Status":
                    embed.set_field_at(i, name="Status", value=status_text, inline=False)
                    status_field_found = True
                    break
            
            if not status_field_found:
                embed.add_field(name="Status", value=status_text, inline=False)
            
            # Update the message
            await message.edit(embed=embed)
            
            # Update in database
            update_suggestion_status(suggestion_id, "rejected")
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "Suggestion Rejected",
                    f"Suggestion #{suggestion_id} has been rejected.",
                    color="error"
                )
            )
            
            # Try to notify the suggester
            try:
                suggester = ctx.guild.get_member(suggestion['user_id'])
                if suggester:
                    await suggester.send(
                        embed=create_embed(
                            "Suggestion Rejected",
                            f"Your suggestion has been rejected by {ctx.author.mention}.",
                            color="error",
                            fields=[
                                {"name": "Your Suggestion", "value": suggestion['content'], "inline": False}
                            ] + ([{"name": "Reason", "value": reason, "inline": False}] if reason else [])
                        )
                    )
            except discord.errors.Forbidden:
                # Can't DM user
                pass
            except Exception as e:
                logger.error(f"Error notifying suggestion author: {e}")
            
        except Exception as e:
            logger.error(f"Error rejecting suggestion: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="consider")
    @commands.check(can_use_suggestion_management)
    async def consider_suggestion(self, ctx, suggestion_id: int, *, comment=None):
        """Mark a suggestion as being considered"""
        suggestion = get_suggestion(suggestion_id)
        
        if not suggestion:
            await ctx.send(f"Suggestion with ID {suggestion_id} not found.")
            return
        
        try:
            # Get the message
            channel = self.bot.get_channel(suggestion['channel_id'])
            if not channel:
                await ctx.send("Suggestion channel not found or not accessible.")
                return
            
            try:
                message = await channel.fetch_message(suggestion['message_id'])
            except (discord.errors.NotFound, discord.errors.Forbidden):
                await ctx.send("Suggestion message not found or not accessible.")
                return
            
            # Update the embed
            embed = message.embeds[0] if message.embeds else discord.Embed(
                title="Suggestion",
                description=suggestion['content']
            )
            
            # Change color to yellow/orange
            embed.color = discord.Color.orange()
            
            # Add status field
            status_text = "⏳ Under Consideration"
            if comment:
                status_text += f"\n\n**Comment:** {comment}"
            
            # Find if there's already a field for status or add a new one
            status_field_found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Status":
                    embed.set_field_at(i, name="Status", value=status_text, inline=False)
                    status_field_found = True
                    break
            
            if not status_field_found:
                embed.add_field(name="Status", value=status_text, inline=False)
            
            # Update the message
            await message.edit(embed=embed)
            
            # Update in database
            update_suggestion_status(suggestion_id, "considering")
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "Suggestion Under Consideration",
                    f"Suggestion #{suggestion_id} has been marked as under consideration.",
                    color="warning"
                )
            )
            
            # Try to notify the suggester
            try:
                suggester = ctx.guild.get_member(suggestion['user_id'])
                if suggester:
                    await suggester.send(
                        embed=create_embed(
                            "Suggestion Under Consideration",
                            f"Your suggestion is being considered by the staff team!",
                            color="warning",
                            fields=[
                                {"name": "Your Suggestion", "value": suggestion['content'], "inline": False}
                            ] + ([{"name": "Comment", "value": comment, "inline": False}] if comment else [])
                        )
                    )
            except discord.errors.Forbidden:
                # Can't DM user
                pass
            except Exception as e:
                logger.error(f"Error notifying suggestion author: {e}")
            
        except Exception as e:
            logger.error(f"Error updating suggestion: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.command(name="implement")
    @commands.check(can_use_suggestion_management)
    async def implement_suggestion(self, ctx, suggestion_id: int, *, comment=None):
        """Mark a suggestion as implemented"""
        suggestion = get_suggestion(suggestion_id)
        
        if not suggestion:
            await ctx.send(f"Suggestion with ID {suggestion_id} not found.")
            return
        
        try:
            # Get the message
            channel = self.bot.get_channel(suggestion['channel_id'])
            if not channel:
                await ctx.send("Suggestion channel not found or not accessible.")
                return
            
            try:
                message = await channel.fetch_message(suggestion['message_id'])
            except (discord.errors.NotFound, discord.errors.Forbidden):
                await ctx.send("Suggestion message not found or not accessible.")
                return
            
            # Update the embed
            embed = message.embeds[0] if message.embeds else discord.Embed(
                title="Suggestion",
                description=suggestion['content']
            )
            
            # Change color to blue
            embed.color = discord.Color.blue()
            
            # Add status field
            status_text = "🚀 Implemented"
            if comment:
                status_text += f"\n\n**Comment:** {comment}"
            
            # Find if there's already a field for status or add a new one
            status_field_found = False
            for i, field in enumerate(embed.fields):
                if field.name == "Status":
                    embed.set_field_at(i, name="Status", value=status_text, inline=False)
                    status_field_found = True
                    break
            
            if not status_field_found:
                embed.add_field(name="Status", value=status_text, inline=False)
            
            # Update the message
            await message.edit(embed=embed)
            
            # Update in database
            update_suggestion_status(suggestion_id, "implemented")
            
            # Send confirmation
            await ctx.send(
                embed=create_embed(
                    "Suggestion Implemented",
                    f"Suggestion #{suggestion_id} has been marked as implemented.",
                    color="info"
                )
            )
            
            # Try to notify the suggester
            try:
                suggester = ctx.guild.get_member(suggestion['user_id'])
                if suggester:
                    await suggester.send(
                        embed=create_embed(
                            "Suggestion Implemented",
                            f"Great news! Your suggestion has been implemented!",
                            color="info",
                            fields=[
                                {"name": "Your Suggestion", "value": suggestion['content'], "inline": False}
                            ] + ([{"name": "Comment", "value": comment, "inline": False}] if comment else [])
                        )
                    )
            except discord.errors.Forbidden:
                # Can't DM user
                pass
            except Exception as e:
                logger.error(f"Error notifying suggestion author: {e}")
            
        except Exception as e:
            logger.error(f"Error updating suggestion: {e}")
            await ctx.send(f"An error occurred: {str(e)}")
    
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        """Handle reactions on suggestion messages"""
        # Ignore bot reactions
        if payload.user_id == self.bot.user.id:
            return
        
        # Check if this is in the suggestions channel
        suggestion_channel_id = self.config.get('channels', {}).get('suggestions')
        if not suggestion_channel_id or payload.channel_id != suggestion_channel_id:
            return
        
        # Check if the reaction is on a suggestion
        suggestion = get_suggestion_by_message(payload.message_id)
        if not suggestion:
            return
        
        # Only track 👍 and 👎 reactions
        if payload.emoji.name not in ["👍", "👎"]:
            # Remove other reactions if not from staff
            try:
                # Get guild and member
                guild = self.bot.get_guild(payload.guild_id)
                if not guild:
                    return
                
                member = guild.get_member(payload.user_id)
                if not member:
                    return
                
                # Check if user is staff
                if not can_use_suggestion_management(member):
                    # Remove the reaction
                    channel = self.bot.get_channel(payload.channel_id)
                    if not channel:
                        return
                    
                    message = await channel.fetch_message(payload.message_id)
                    if not message:
                        return
                    
                    await message.remove_reaction(payload.emoji, member)
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
            except Exception as e:
                logger.error(f"Error handling suggestion reaction: {e}")

async def setup(bot):
    await bot.add_cog(Suggestions(bot))
