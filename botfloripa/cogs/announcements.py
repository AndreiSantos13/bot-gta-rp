import discord
from discord.ext import commands
import asyncio
import logging
from datetime import datetime

from utils.helpers import (
    create_embed, load_config, can_use_announcement_commands
)

logger = logging.getLogger("bot.announcements")

class Announcements(commands.Cog):
    """Handles announcement commands for server staff"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = load_config()
    
    @commands.command(name="announce")
    @commands.check(can_use_announcement_commands)
    async def announce(self, ctx, *, message=None):
        """Send an announcement to the configured channel"""
        # Cancel if no message was provided
        if not message:
            await ctx.send("Please provide a message to announce. Usage: `!announce <message>`")
            return
        
        # Get the announcement channel from config
        announcement_channel_id = self.config.get('channels', {}).get('announcements')
        if not announcement_channel_id:
            # If no channel configured, ask for one
            await ctx.send(
                "No announcement channel configured. Please specify a channel to send to."
                "\nUsage: `!announce #channel <message>`"
            )
            return
        
        channel = ctx.guild.get_channel(announcement_channel_id)
        
        # If channel isn't found, check if it's in the message
        if not channel and ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
            # Remove the channel mention from the message
            message = message.replace(f"<#{channel.id}>", "", 1).strip()
        
        if not channel:
            await ctx.send(
                "Announcement channel not found or not accessible. Please configure it in the settings"
                " or mention a channel in your command."
            )
            return
        
        # Confirm announcement details and ask for confirmation
        confirmation_embed = create_embed(
            "Announcement Preview",
            "Please review this announcement and confirm by reacting with ✅ or cancel with ❌.",
            color="info"
        )
        
        # Create announcement embed
        announcement_embed = create_embed(
            "Server Announcement",
            message,
            color="info"
        )
        announcement_embed.set_footer(text=f"Announced by {ctx.author.name}")
        
        # Add fields showing where this will be sent
        confirmation_embed.add_field(
            name="Will be sent to", 
            value=f"{channel.mention} (`{channel.name}`)",
            inline=True
        )
        
        # Send confirmation message with preview
        confirmation_message = await ctx.send(embeds=[confirmation_embed, announcement_embed])
        await confirmation_message.add_reaction("✅")
        await confirmation_message.add_reaction("❌")
        
        # Wait for confirmation
        def check(reaction, user):
            return (
                user == ctx.author and 
                reaction.message.id == confirmation_message.id and
                str(reaction.emoji) in ["✅", "❌"]
            )
        
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            
            if str(reaction.emoji) == "✅":
                # Send the announcement
                try:
                    # Check if the message mentions @everyone or @here explicitly
                    mention_everyone = False
                    if "@everyone" in message or "@here" in message:
                        mention_everyone = True
                        # Ask for additional confirmation for mass mentions
                        await ctx.send(
                            "⚠️ This announcement contains a mass mention (@everyone or @here). Are you sure? (yes/no)"
                        )
                        
                        def confirm_check(m):
                            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no", "y", "n"]
                        
                        try:
                            confirm_msg = await self.bot.wait_for("message", timeout=30.0, check=confirm_check)
                            if confirm_msg.content.lower() not in ["yes", "y"]:
                                await ctx.send("Announcement cancelled.")
                                return
                        except asyncio.TimeoutError:
                            await ctx.send("Confirmation timed out. Announcement cancelled.")
                            return
                    
                    announcement = await channel.send(
                        content="" if not mention_everyone else None,
                        embed=announcement_embed,
                        allowed_mentions=discord.AllowedMentions(everyone=mention_everyone, roles=True, users=True)
                    )
                    
                    # Send confirmation
                    await ctx.send(
                        embed=create_embed(
                            "Announcement Sent",
                            f"Your announcement has been sent to {channel.mention}.\n[Jump to announcement]({announcement.jump_url})",
                            color="success"
                        )
                    )
                except discord.errors.Forbidden:
                    await ctx.send("I don't have permission to send messages to that channel.")
                except Exception as e:
                    logger.error(f"Error sending announcement: {e}")
                    await ctx.send(f"An error occurred: {str(e)}")
            else:
                # Cancelled
                await ctx.send("Announcement cancelled.")
                
        except asyncio.TimeoutError:
            await ctx.send("Confirmation timed out. Announcement cancelled.")
    
    @commands.command(name="embed")
    @commands.check(can_use_announcement_commands)
    async def create_embed(self, ctx):
        """Create a custom embed interactively"""
        # Start interactive embed creation
        await ctx.send(
            embed=create_embed(
                "Embed Creator",
                "Let's create a custom embed. I'll ask you for each piece of information.\n"
                "Type `cancel` at any time to cancel the process.\n"
                "Type `skip` to skip a field and leave it empty.",
                color="info"
            )
        )
        
        # Helper function for getting responses
        async def get_response(prompt, timeout=120):
            await ctx.send(prompt)
            
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel
            
            try:
                response = await self.bot.wait_for("message", timeout=timeout, check=check)
                
                if response.content.lower() == "cancel":
                    await ctx.send("Embed creation cancelled.")
                    return None
                
                if response.content.lower() == "skip":
                    return ""
                
                return response.content
            except asyncio.TimeoutError:
                await ctx.send("Timed out. Embed creation cancelled.")
                return None
        
        # Get fields one by one
        title = await get_response("What should the **title** of the embed be?")
        if title is None:
            return
        
        description = await get_response("What should the **description** of the embed be? This can be longer text.")
        if description is None:
            return
        
        color_input = await get_response(
            "What **color** should the embed be? Choose one: `red`, `green`, `blue`, `orange`, `purple`, or `skip` for default."
        )
        if color_input is None:
            return
        
        # Convert color name to hex
        color_map = {
            "red": 0xE74C3C,
            "green": 0x2ECC71,
            "blue": 0x3498DB,
            "orange": 0xE67E22,
            "purple": 0x9B59B6,
            "": None  # Default
        }
        color = color_map.get(color_input.lower(), color_map[""])
        
        # Ask for fields
        fields = []
        adding_fields = True
        
        while adding_fields:
            add_field = await get_response("Would you like to add a field? (yes/no)")
            if add_field is None:
                return
            
            if add_field.lower() not in ["yes", "y"]:
                adding_fields = False
                continue
            
            field_name = await get_response("What should the **field name** be?")
            if field_name is None:
                return
            
            field_value = await get_response("What should the **field value** be?")
            if field_value is None:
                return
            
            field_inline = await get_response("Should this field be inline? (yes/no)")
            if field_inline is None:
                return
            
            fields.append({
                "name": field_name,
                "value": field_value,
                "inline": field_inline.lower() in ["yes", "y"]
            })
        
        # Ask for footer
        footer = await get_response("What should the **footer** of the embed be? (Type `skip` to use the default server name)")
        if footer is None:
            return
        
        # Create the embed
        embed = create_embed(
            title,
            description,
            color=color,
            fields=fields,
            footer=footer if footer else None
        )
        
        # Ask for target channel
        channel_prompt = "Where should I send this embed? Mention a channel or type `here` for the current channel."
        channel_response = await get_response(channel_prompt)
        if channel_response is None:
            return
        
        if channel_response.lower() == "here":
            target_channel = ctx.channel
        elif ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
        else:
            # Try to find channel by name
            target_channel = discord.utils.get(ctx.guild.text_channels, name=channel_response)
            if not target_channel:
                await ctx.send(f"Could not find channel '{channel_response}'. Sending to current channel instead.")
                target_channel = ctx.channel
        
        # Show preview and confirm
        preview_message = await ctx.send("Preview of your embed:", embed=embed)
        await preview_message.add_reaction("✅")
        await preview_message.add_reaction("❌")
        
        confirmation_message = await ctx.send(f"React with ✅ to send to {target_channel.mention} or ❌ to cancel.")
        
        # Wait for confirmation
        def check(reaction, user):
            return (
                user == ctx.author and 
                reaction.message.id == preview_message.id and
                str(reaction.emoji) in ["✅", "❌"]
            )
        
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            
            if str(reaction.emoji) == "✅":
                # Send the embed
                try:
                    await target_channel.send(embed=embed)
                    await ctx.send(
                        embed=create_embed(
                            "Success",
                            f"Your embed has been sent to {target_channel.mention}.",
                            color="success"
                        )
                    )
                except discord.errors.Forbidden:
                    await ctx.send("I don't have permission to send messages to that channel.")
                except Exception as e:
                    logger.error(f"Error sending embed: {e}")
                    await ctx.send(f"An error occurred: {str(e)}")
            else:
                # Cancelled
                await ctx.send("Embed creation cancelled.")
                
        except asyncio.TimeoutError:
            await ctx.send("Confirmation timed out. Embed creation cancelled.")

async def setup(bot):
    await bot.add_cog(Announcements(bot))
