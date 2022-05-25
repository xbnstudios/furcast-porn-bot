# FurCast Porn Bot

Manages the FurCast NSFW channel

## How to use

The bot must be an administrator in both the main group (for /nsfw) and the
NSFW channel (for posting).
* Main group: Delete messages
* NSFW channel: Send messages, Add members

See the old
[furcast-tg-bot setup instructions](https://github.com/xbnstudios/furcast-tg-bot/blob/0921ef053b3abd9b28127de7b175d3ee303f403b/README.md#how-to-use).
This bot will not work properly on GCF, since GCF kills applications
aggressively and this is not written to persist its conversation state.

## Commands
None are registered with BotFather. The only end-user command is /start, which
is automatically prompted by Telegram.
```
cancel - (PM) Cancel a draft post
newlink - (Admin group) Rotate the NSFW chat's invite link
nsfw - (Main) Reply to a NSFW post with `/nsfw cheetah butt` to move it to NSFW
start - (PM) Request an invite to the NSFW channel
version - Show source link and GCF version
```
