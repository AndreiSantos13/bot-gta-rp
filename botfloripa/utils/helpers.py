import discord
import json
import logging
from datetime import datetime, timedelta
import re

logger = logging.getLogger("bot.helpers")

def load_config():
    """Load the configuration from the config.json file"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}

def create_embed(title, description, color=None, fields=None, footer=None, thumbnail=None):
    """Create a Discord embed with the given parameters"""
    config = load_config()
    
    # Default to info color if not specified
    if color is None:
        color = int(config.get('color', {}).get('info', '0x3498db'), 16)
    elif isinstance(color, str):
        if color in config.get('color', {}):
            color = int(config.get('color', {}).get(color, '0x3498db'), 16)
        elif color.startswith('0x'):
            color = int(color, 16)
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now().astimezone()
    )
    
    # Add fields if provided
    if fields:
        for field in fields:
            embed.add_field(
                name=field.get('name', 'Field'),
                value=field.get('value', 'Value'),
                inline=field.get('inline', False)
            )
    
    # Set footer if provided
    if footer:
        embed.set_footer(text=footer)
    else:
        config = load_config()
        embed.set_footer(text=config.get('server_name', 'GTA RP Server'))
    
    # Set thumbnail if provided
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    
    return embed

def parse_time(time_str):
    """
    Parse time string like "1d", "2h", "30m" into timedelta
    Returns None if the format is invalid
    """
    if not time_str:
        return None
    
    time_regex = re.compile(r'(\d+)([dhms])')
    match = time_regex.match(time_str.lower())
    
    if not match:
        return None
    
    amount, unit = match.groups()
    amount = int(amount)
    
    if unit == 'd':
        return timedelta(days=amount)
    elif unit == 'h':
        return timedelta(hours=amount)
    elif unit == 'm':
        return timedelta(minutes=amount)
    elif unit == 's':
        return timedelta(seconds=amount)
    
    return None

def format_time_difference(dt):
    """Format a datetime to show time from now"""
    if not dt:
        return "N/A"
    
    now = datetime.now().astimezone()
    
    # Convert string to datetime if needed
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
            # Se a data não tem fuso horário, adicione
            if dt.tzinfo is None:
                dt = dt.astimezone()
        except ValueError:
            return dt
    
    diff = dt - now if dt > now else now - dt
    
    days = diff.days
    hours, remainder = divmod(diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{days} days, {hours} hours"
    elif hours > 0:
        return f"{hours} hours, {minutes} minutes"
    elif minutes > 0:
        return f"{minutes} minutes, {seconds} seconds"
    else:
        return f"{seconds} seconds"

def is_admin(member):
    """Check if a member has admin permissions"""
    config = load_config()
    admin_role_id = config.get('roles', {}).get('admin')
    
    # If admin role is configured, check for it
    if admin_role_id:
        return any(role.id == admin_role_id for role in member.roles)
    
    # Fallback to checking for administrator permission
    return member.guild_permissions.administrator

def is_moderator(member):
    """Check if a member has moderator permissions"""
    config = load_config()
    admin_role_id = config.get('roles', {}).get('admin')
    mod_role_id = config.get('roles', {}).get('moderator')
    
    # Check for admin role first
    if admin_role_id and any(role.id == admin_role_id for role in member.roles):
        return True
    
    # Then check for moderator role
    if mod_role_id and any(role.id == mod_role_id for role in member.roles):
        return True
    
    # Fallback to checking for management permissions
    return (member.guild_permissions.administrator or 
            member.guild_permissions.ban_members or 
            member.guild_permissions.kick_members)

def can_use_allowlist_commands(member):
    """Check if member can use allowlist commands"""
    # Either admin or mod can use allowlist commands
    return is_admin(member) or is_moderator(member)

def can_use_moderation_commands(member):
    """Check if member can use moderation commands"""
    # Either admin or mod can use moderation commands
    return is_admin(member) or is_moderator(member)

def can_use_announcement_commands(member):
    """Check if member can use announcement commands"""
    # Only admins can use announcement commands by default
    return is_admin(member)

def can_use_suggestion_management(member):
    """Check if member can manage suggestions"""
    # Either admin or mod can manage suggestions
    return is_admin(member) or is_moderator(member)

def get_channel_id(channel_type):
    """Get a channel ID from the config"""
    config = load_config()
    return config.get('channels', {}).get(channel_type)
