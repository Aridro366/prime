🧠 Wemplify Discord Bot

A powerful multipurpose Discord bot written in Python (discord.py) with modular Cogs, MongoDB integration, and advanced moderation, utility, and logging features.

⚙️ Features
🛡️ Moderation

/warn, /mute, /unmute, /kick, /ban, /unban

Automatic 24-hour timeout after 3 warnings

/purge — bulk delete messages

/link_blocker_on & /link_blocker_off — auto-warns link senders

/mod_logs_channel — set per-server mod logs channel

Sends DM to users on warn, mute, kick, ban, etc.

🧰 Server Tools

/addrole and /removerole

.status — owner-only command to change bot’s activity

Guild-specific log channels for moderation & server actions

⚙️ Logging System

Separate logging for:

🟢 Bot Logs — startup, errors

⚙️ Command Logs — command usage and failures

🏠 Server Logs — server joins/leaves

Configurable channel IDs or database-based setup

🧍 Utility

AFK system (/afk and /afkremove) showing time away

Auto DM notifications for moderation actions

🛠️ Installation
1. Clone the Repository
git clone https://github.com/yourusername/wemplify.git
cd wemplify

2. Install Requirements
pip install -r requirements.txt


*(Make sure you’re using Python 3.10+)

3. Create a .env File
DISCORD_TOKEN=your_discord_bot_token
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?appName=Prime

⚙️ Project Structure
📁 wemplify/
├── main.py                # Bot launcher
├── config.json            # Config (prefix, owner_id, etc.)
├── cogs/
│   ├── moderation.py      # All moderation commands
│   ├── utility.py         # AFK, user tools
│   ├── server_tools.py    # Roles, status management
│   └── ...
├── requirements.txt
└── README.md

⚙️ Run the Bot
python main.py

⚡ Commands Overview
🔧 Prefix Commands
Command	Description
.status <text>	Change bot’s status (Owner only)
🛡️ Moderation
Slash Command	Description
/warn <user> <reason>	Warns a user
/mute <user> <time>	Temporarily mutes user
/unmute <user>	Removes mute
/kick <user> <reason>	Kicks user
/ban <user> <reason>	Bans user
/unban <user>	Unbans user
/purge <amount>	Deletes recent messages
/link_blocker_on	Enable link-block protection
/link_blocker_off	Disable link-block protection
/mod_logs_channel <channel>	Set mod log channel
🧰 Server Tools
Slash Command	Description
/addrole <user> <role>	Add a role to a user
/removerole <user> <role>	Remove a role from a user


Or via /set_bot_log, /set_cmd_log, /set_server_log (if you enabled DB logging per guild).

🛠️ Tech Stack

Python 3.10+

discord.py (v2.4+)

Motor (async MongoDB driver)

dotenv for environment variables

💬 Support & Contact

If you encounter issues or want to contribute, open an issue on the repository
or join the official Discord support server (link here).