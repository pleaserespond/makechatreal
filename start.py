import logging, logging.handlers
import os
import random
import sqlite3
import sys
import time
import discord, discord.ext, discord.ext.commands, discord.ext.tasks

def setup_logging():
    '''
    Setup logging to stderr and rotating log file with log level customisable
    by LOGLEVEL env variable.
    '''
    loglevel = os.getenv('LOGLEVEL')
    if not loglevel:
        loglevel = logging.INFO
    logging.basicConfig(stream=sys.stderr, level=loglevel)
    file_handler = logging.handlers.RotatingFileHandler(
        filename='makechatreal.log', maxBytes=1024*1024)
    file_handler.setLevel(loglevel)
    logging.getLogger(None).addHandler(file_handler)


def create_db():
    '''
    Create sqlite3 database if it doesn't exist and return connection to it.
    '''
    db = sqlite3.connect('makechatreal.db')
    db.cursor().execute('CREATE TABLE IF NOT EXISTS lastchange (name text, time integer)')
    return db


def get_lastchange(log, cur, name):
    sel = cur.execute('SELECT time FROM lastchange WHERE name=?', (name,))
    row = sel.fetchone()
    result = 0
    if row is None:
        log.info('Creating record for guild %s', name)
        cur.execute('INSERT INTO lastchange VALUES (?, ?)', (name, 0))
    else:
        result = row[0]
    return result


INTERVAL = 24*60*60
CHATTERS = 10


async def rejigger_guild(log, cur, guild):
    global INTERVAL
    global CHATTERS
    name = guild.name
    chat_role = None
    for role in guild.roles:
        if role.name == 'chat':
            chat_role = role
            break
    else:
        log.info('Creating role "chat" in guild %s', name)
        chat_role = await guild.create_role(name='chat')
    now = int(time.time())
    lastchange = get_lastchange(log, cur, name)
    if lastchange + INTERVAL > now:
        # Update is in the future
        return
    log.info('Rejiggering guild %s', name)
    all_users = []
    chat_members = []
    async for user in guild.fetch_members():
        if user.bot:
            continue
        for role in user.roles:
            if role.id == chat_role.id:
                chat_members.append(user)
                break
        else:
            all_users.append(user)
    log.info('Guild %s: current chatters %d available victims %d', name, len(chat_members), len(all_users))
    new_chatters = None
    if len(all_users) < CHATTERS:
        # Not enough members, pick a few at random from current chatters
        new_chatters = chat_members[:]
        random.shuffle(new_chatters)
        new_chatters = new_chatters[:CHATTERS - len(all_users)] + all_users
    else:
        random.shuffle(all_users)
        new_chatters = all_users[:CHATTERS]
    for user in chat_members:
        if user in new_chatters:
            continue
        log.info('Guild %s: removing user %s from chat', name, user.name)
        await user.remove_roles(chat_role)
    for user in new_chatters:
        if user in chat_members:
            continue
        log.info('Guild %s: adding user %s to chat', name, user.name)
        await user.add_roles(chat_role)
    cur.execute('UPDATE lastchange SET time=? WHERE name=?', (now, guild.name))


def start():
    setup_logging()
    db = create_db()
    log = logging.getLogger('makechatreal')

    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        log.error('Env variable DISCORD_TOKEN not set')
        return 1
    intents = discord.Intents()
    # Needed to read guild name
    intents.guilds = True
    # Needed to read list of members
    intents.members = True
    # Not used right now, possibly for configuration in the future
    # Note: this only lets the bot read contents of messages that @-mention it
    # explicitly, but it does receive an event for each message.
    intents.messages = True
    bot = discord.ext.commands.Bot(command_prefix='!', intents=intents)
    log.info('Intents value: %d', bot.intents.value)

    @discord.ext.tasks.loop(seconds=60*60)
    async def on_timer():
        log.info('Rejiggering users')
        for guild in bot.guilds:
            cur = db.cursor()
            await rejigger_guild(log, cur, guild)
            del cur
            db.commit()
        log.info('Done rejiggering')

    @bot.event
    async def on_ready():
        log.info('Connected!')
        log.info('Member of: %s', ', '.join([guild.name for guild in bot.guilds]))
        on_timer.start()

    @bot.event
    async def on_message(msg):
        pass
        #log.info('Received message from %s: %s', msg.author.name, msg.content)

    log.info('Connecting to Discord...')
    bot.run(TOKEN)


if __name__ == '__main__':
    ret = start()
    if ret != 0:
        sys.exit(ret)

# vim:ai:si:et:sw=4 ts=4

