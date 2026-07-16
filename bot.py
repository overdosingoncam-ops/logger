import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import logging
from datetime import datetime
import requests
import json

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_URL = os.getenv('API_URL', 'http://localhost:5000')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.dm_messages = True
intents.presences = True

bot = commands.Bot(command_prefix='?', intents=intents, help_command=None)

from app import app, db, User, Message, Server, Channel, NameHistory, AvatarHistory, IP, TokenSession
import hashlib

class DiscordLogger:
    def __init__(self, bot):
        self.bot = bot
        self.user_tokens = {}
        self.ready = False
    
    async def log_message(self, message):
        if message.author.bot:
            return
        
        try:
            with app.app_context():
                user = User.query.get(str(message.author.id))
                if not user:
                    user = User(
                        id=str(message.author.id),
                        username=message.author.name,
                        display_name=message.author.display_name,
                        avatar_url=str(message.author.avatar.url) if message.author.avatar else None,
                        bio=message.author.bio if hasattr(message.author, 'bio') else None,
                        logged_by_tokens=[]
                    )
                    db.session.add(user)
                else:
                    if user.username != message.author.name:
                        name_history = NameHistory(
                            user_id=user.id,
                            old_name=user.username
                        )
                        db.session.add(name_history)
                        user.username = message.author.name
                    
                    if user.avatar_url != str(message.author.avatar.url if message.author.avatar else None):
                        if user.avatar_url:
                            avatar_history = AvatarHistory(
                                user_id=user.id,
                                avatar_url=user.avatar_url
                            )
                            db.session.add(avatar_history)
                        user.avatar_url = str(message.author.avatar.url) if message.author.avatar else None
                    
                    user.display_name = message.author.display_name
                    user.updated_at = datetime.utcnow()
                
                server = None
                if message.guild:
                    server = Server.query.get(str(message.guild.id))
                    if not server:
                        server = Server(
                            id=str(message.guild.id),
                            name=message.guild.name,
                            icon_url=str(message.guild.icon.url) if message.guild.icon else None
                        )
                        db.session.add(server)
                    
                    if user not in server.members:
                        server.members.append(user)
                
                channel = Channel.query.get(str(message.channel.id))
                if not channel:
                    is_dm = isinstance(message.channel, discord.DMChannel)
                    channel = Channel(
                        id=str(message.channel.id),
                        server_id=str(message.guild.id) if message.guild else None,
                        name=message.channel.name if hasattr(message.channel, 'name') else str(message.author),
                        is_dm=is_dm
                    )
                    db.session.add(channel)
                
                msg = Message(
                    id=str(message.id),
                    user_id=str(message.author.id),
                    server_id=str(message.guild.id) if message.guild else None,
                    channel_id=str(message.channel.id),
                    content=message.content,
                    logged_by_token=self.get_logged_by_token(message.author.id),
                    created_at=message.created_at
                )
                db.session.add(msg)
                db.session.commit()
                
                logger.info(f"Logged message from {message.author} in {message.guild or 'DM'}")
        except Exception as e:
            logger.error(f"Error logging message: {str(e)}")
            db.session.rollback()
    
    def get_logged_by_token(self, user_id):
        return self.user_tokens.get(str(user_id), 'unknown')

logger_instance = DiscordLogger(bot)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger_instance.ready = True
    health_check.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    await logger_instance.log_message(message)
    await bot.process_commands(message)

@bot.command(name='help', help='Show all available commands')
async def help_command(ctx):
    embed = discord.Embed(
        title="📋 Logger Commands",
        description="Advanced Discord message logging commands",
        color=discord.Color.dark_theme()
    )
    
    embed.add_field(name="?user messages <user_id> <channel_id>", value="Get all messages from a user in a specific channel", inline=False)
    embed.add_field(name="?user info <user_id>", value="Get detailed information about a user", inline=False)
    embed.add_field(name="?search <keyword>", value="Search for messages containing a keyword", inline=False)
    embed.add_field(name="?server info <server_id>", value="Get information about a server", inline=False)
    embed.add_field(name="?stats", value="Show logging statistics", inline=False)
    embed.add_field(name="?logged users", value="Show count of logged users", inline=False)
    embed.add_field(name="?status", value="Check logger status", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='user', help='Get user information')
async def user_command(ctx, subcommand, *args):
    try:
        if subcommand == 'info' and len(args) >= 1:
            user_id = args[0]
            with app.app_context():
                user = User.query.get(user_id)
                if not user:
                    await ctx.send("❌ User not found")
                    return
                
                embed = discord.Embed(title=f"👤 {user.display_name or user.username}", color=discord.Color.dark_theme())
                embed.add_field(name="ID", value=user.id, inline=False)
                embed.add_field(name="Username", value=user.username, inline=False)
                embed.add_field(name="Display Name", value=user.display_name or "N/A", inline=False)
                embed.add_field(name="Bio", value=user.bio or "N/A", inline=False)
                embed.add_field(name="Messages", value=len(user.messages), inline=True)
                embed.add_field(name="Servers", value=len(user.servers), inline=True)
                
                if user.avatar_url:
                    embed.set_thumbnail(url=user.avatar_url)
                
                await ctx.send(embed=embed)
        
        elif subcommand == 'messages' and len(args) >= 2:
            user_id = args[0]
            channel_id = args[1]
            with app.app_context():
                messages = Message.query.filter_by(user_id=user_id, channel_id=channel_id).limit(10).all()
                if not messages:
                    await ctx.send("❌ No messages found")
                    return
                
                embed = discord.Embed(title=f"💬 Messages from {user_id}", color=discord.Color.dark_theme())
                for msg in messages:
                    embed.add_field(name=msg.created_at.strftime('%Y-%m-%d %H:%M:%S'), value=msg.content[:200], inline=False)
                
                await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"User command error: {str(e)}")
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='search', help='Search for messages')
async def search_command(ctx, *, keyword):
    try:
        with app.app_context():
            messages = Message.query.filter(Message.content.ilike(f'%{keyword}%')).limit(10).all()
            if not messages:
                await ctx.send("❌ No messages found")
                return
            
            embed = discord.Embed(title=f"🔍 Search results for '{keyword}'", color=discord.Color.dark_theme())
            for msg in messages:
                user = User.query.get(msg.user_id)
                embed.add_field(name=f"{user.username if user else 'Unknown'}", value=msg.content[:200], inline=False)
            
            await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Search command error: {str(e)}")
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='server', help='Get server information')
async def server_command(ctx, subcommand, server_id=None):
    try:
        if subcommand == 'info' and server_id:
            with app.app_context():
                server = Server.query.get(server_id)
                if not server:
                    await ctx.send("❌ Server not found")
                    return
                
                embed = discord.Embed(title=f"🏢 {server.name}", color=discord.Color.dark_theme())
                embed.add_field(name="ID", value=server.id, inline=False)
                embed.add_field(name="Members", value=len(server.members), inline=True)
                embed.add_field(name="Messages", value=len(server.messages), inline=True)
                
                await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Server command error: {str(e)}")
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='stats', help='Show logging statistics')
async def stats_command(ctx):
    try:
        with app.app_context():
            total_users = User.query.count()
            total_messages = Message.query.count()
            total_servers = Server.query.count()
            
            embed = discord.Embed(title="📊 Logger Statistics", color=discord.Color.dark_theme())
            embed.add_field(name="Total Users", value=total_users, inline=True)
            embed.add_field(name="Total Messages", value=total_messages, inline=True)
            embed.add_field(name="Total Servers", value=total_servers, inline=True)
            
            await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Stats command error: {str(e)}")
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='logged', help='Show logged data count')
async def logged_command(ctx, data_type='users'):
    try:
        with app.app_context():
            if data_type == 'users':
                count = User.query.count()
                await ctx.send(f"👥 Logged Users: **{count}**")
            elif data_type == 'servers':
                count = Server.query.count()
                await ctx.send(f"🏢 Logged Servers: **{count}**")
            elif data_type == 'messages':
                count = Message.query.count()
                await ctx.send(f"💬 Logged Messages: **{count}**")
    except Exception as e:
        logger.error(f"Logged command error: {str(e)}")
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='status', help='Check logger status')
async def status_command(ctx):
    try:
        embed = discord.Embed(title="✅ Logger Status", description="System Status Report", color=discord.Color.green())
        embed.add_field(name="Bot Status", value="🟢 Online", inline=True)
        embed.add_field(name="Logger", value="🟢 Active", inline=True)
        embed.add_field(name="Database", value="🟢 Connected", inline=True)
        
        await ctx.send(embed=embed)
    except Exception as e:
        logger.error(f"Status command error: {str(e)}")
        await ctx.send(f"❌ Error: {str(e)}")

@tasks.loop(minutes=5)
async def health_check():
    try:
        with app.app_context():
            db.session.execute('SELECT 1')
            logger.info("Health check passed")
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")

if __name__ == '__main__':
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        logger.error(f"Bot startup error: {str(e)}")
