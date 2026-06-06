#!/usr/bin/env python3

from __future__ import annotations

from datetime import timedelta
from html import escape
from json import dumps as json_dumps
import logging
import os
import traceback

from dotenv import load_dotenv
from telegram import (
    Bot,
    ChatMemberAdministrator,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    Update,
    User,
)
from telegram.constants import ParseMode
import telegram.error
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    filters,
    MessageHandler,
)

load_dotenv()
if "TELEGRAM_TOKEN" not in os.environ or "APIKEY" not in os.environ:
    logging.error("You forgot to set one of the environment vars!")
    exit(3)

# Parsed as HTML - be sure to escape anything you put in!
join_template = (
    "Hello, {escaped_fname}! The "
    "<a href='https://furcast.fm/chat/#rules'>rules</a> still apply for "
    "content posted via this bot! Just send me media to post. "
    "Your channel invite link is below. Use it before it expires!"
)
button_text = "CLICK ME OH YEAH JUST LIKE THAT"


class Chats(object):
    furcast = -1001462860928
    furcast_nsfw = -1001174373210
    xbn_chatops = -1001498895240
    riley_test_channel = -1001263448135
    riley_test_group = -1001422900025


if os.environ.get("TEST_MODE") in [None, 0]:
    porn_chat_id = Chats.furcast_nsfw
    main_chat_id = Chats.furcast
    invite_chat_id = Chats.furcast_nsfw
    admin_chat_id = Chats.xbn_chatops
else:
    porn_chat_id = Chats.riley_test_channel
    main_chat_id = Chats.riley_test_group
    invite_chat_id = Chats.riley_test_channel
    admin_chat_id = Chats.xbn_chatops

join_link = os.environ.get("JOIN_LINK")
apikey = os.environ["APIKEY"]


logging.basicConfig(level=logging.INFO)

POST_MEDIA, POST_DESCRIPTION = range(2)


async def in_main_chat(bot: Bot, user: User) -> bool:
    """Validate a user's presence in the main chat"""

    try:
        main_chat = await bot.get_chat(main_chat_id)
        main_chat_user = await main_chat.get_member(user.id)
    except telegram.error.BadRequest as e:
        logging.warning(
            "Error finding user %s (%s): %s",
            user.name,
            user.id,
            e,
        )
        main_chat_user = None
    if main_chat_user is None or main_chat_user.status not in [
        "member",
        "administrator",
        "creator",
    ]:
        logging.warning(
            "User not in main chat: %s (%s): %s",
            user.name,
            user.id,
            main_chat_user,
        )
        return False
    return True


async def post_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if not update.effective_user or not update.message or context.user_data is None:
        raise AttributeError("Missing required attributes")

    logging.debug(
        "post_cancel: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    del context.user_data["media"]
    await update.message.reply_text("Cancelled")
    return ConversationHandler.END


async def post_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int | None:
    if not update.effective_user or not update.message or context.user_data is None:
        raise AttributeError("Missing required attributes")

    logging.debug(
        "post_description: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    await do_nsfw_post(
        context.bot, context.user_data["media"], update.message.text_html
    )
    del context.user_data["media"]
    await update.message.reply_text("Thanks, posted!")
    return ConversationHandler.END


async def post_description_error(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int | None:
    if not update.effective_user or not update.message:
        raise AttributeError("Missing required attributes")

    logging.debug(
        "post_description_error: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    await update.message.reply_text(
        "Sorry, descriptions must be text. Send a text description, or /cancel"
    )
    return POST_DESCRIPTION


async def post_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if not update.effective_user or not update.message or context.user_data is None:
        raise AttributeError("Missing required attributes")

    logging.debug(
        "post_media: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    if not await in_main_chat(context.bot, update.effective_user):
        await update.message.reply_text("Sorry, this bot serves a private group.")
        return None
    context.user_data["media"] = update.message
    await update.message.reply_html(
        "Now tell me the <b>content warnings</b> and <b>tags</b>, e.g.\n"
        "• irl sexytimes with my mate\n"
        "• anthro mouse getting vored\n"
        "• fisting cute anthro wolf\n"
        "(or /cancel)"
    )
    return POST_DESCRIPTION


async def post_media_error(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int | None:
    if not update.effective_user or not update.message:
        raise AttributeError("Missing required attributes")

    logging.debug(
        "post_media_error: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    if not await in_main_chat(context.bot, update.effective_user):
        await update.message.reply_text("Sorry, this bot serves a private group.")
        return None
    await update.message.reply_text(
        "Hi, I help you share NSFW content. This system is meant for media, "
        "which I didn't see in what you sent. If I forgot what we were "
        "talking about, try again. If you need an invite link to the NSFW "
        "channel, say /start. If you think this is a bug, contact the admins."
    )
    return ConversationHandler.END


async def post_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if not update.effective_user or not update.message:
        raise AttributeError("Missing required attributes")

    logging.debug(
        "post_post: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    await update.message.reply_text("Just send me the media you want to share!")
    return POST_MEDIA


async def post_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        raise AttributeError("Missing required attributes")
    logging.debug(
        "post_timeout: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    await update.message.reply_text("Sorry, your last post timed out, try again.")


media_filters = (
    filters.Entity(MessageEntity.URL)  # Plain URL
    | filters.Entity(MessageEntity.TEXT_LINK)  # Formatted link
    | filters.ANIMATION
    | filters.AUDIO
    | filters.Document.ALL
    | filters.PHOTO
    | filters.Sticker.ALL
    | filters.VIDEO
    | filters.VIDEO_NOTE  # "Telescope" video
    | filters.VOICE  # Voice notes
)
pm_nonedit = ~filters.UpdateType.EDITED_MESSAGE & filters.ChatType.PRIVATE
post_handler = ConversationHandler(
    entry_points=[
        # CommandHandler("post", post_post, pm_nonedit),
        MessageHandler(pm_nonedit & media_filters, post_media),
        MessageHandler(pm_nonedit & ~media_filters, post_media_error),
    ],
    states={
        POST_MEDIA: [
            MessageHandler(pm_nonedit & media_filters, post_media),
            MessageHandler(pm_nonedit & ~media_filters, post_media_error),
        ],
        POST_DESCRIPTION: [
            CommandHandler("cancel", post_cancel, pm_nonedit),
            MessageHandler(pm_nonedit & filters.TEXT, post_description),
            MessageHandler(pm_nonedit & ~filters.TEXT, post_description_error),
        ],
        ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, post_timeout)],
    },
    fallbacks=[CommandHandler("cancel", post_cancel, pm_nonedit)],
    conversation_timeout=timedelta(minutes=3),
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot /start callback
    Gives user invite link button"""

    if not update.effective_chat or not update.effective_user or not update.message:
        raise AttributeError("Missing required attributes")

    logging.info(
        "Inviting %s (%s, %s)",
        update.effective_user.username,
        update.effective_user.full_name,
        update.effective_user.id,
    )

    if not await in_main_chat(context.bot, update.effective_user):
        await update.message.reply_text("Sorry, this bot serves a private group.")
        return

    # Send link
    await update.message.reply_html(
        text=join_template.format(
            escaped_fname=escape(update.effective_user.first_name)
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=button_text, url=join_link)]]
        ),
        disable_web_page_preview=True,
    )


async def nsfw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot /nsfw callback
    Moves a post to the NSFW channel"""

    if (
        not update.effective_chat
        or not update.effective_user
        or not update.effective_message
    ):
        raise AttributeError("Missing required attributes")

    if update.effective_chat.id != main_chat_id:
        await update.effective_message.reply_text(
            "Sorry, this command only works in the main chat."
        )
        return

    message = update.effective_message
    move_message = message.reply_to_message
    if message.message_thread_id and not move_message:
        # already moved/deleted
        return
    if not move_message:
        await message.reply_text(
            "You forgot to reply to the message that needs to be moved!"
        )
        return

    chat_user = await context.bot.get_chat_member(
        main_chat_id, update.effective_user.id
    )
    chatop = (
        isinstance(chat_user, ChatMemberAdministrator)
        and chat_user.can_delete_messages
        or chat_user.status == "creator"
    )
    if not (
        # This is a stupid hack because MessageFilter|MessageFilter=MergedFilter,
        # which is an UpdateFilter...
        media_filters.check_update(Update(0, move_message))
        or chatop
    ):
        await message.reply_text("Only media can be moved")
        return

    moving_own_message = (
        move_message.from_user and move_message.from_user.id == update.effective_user.id
    )
    if not chatop and not moving_own_message:
        await message.reply_text(
            "Sorry, command is for your own messages or admins. "
            "Please @ an admin if someone else's post should be moved."
        )
        return

    parts = message.text_html.strip().split(" ", 1)
    description = "(moved from main chat)"
    if not (len(parts) > 1 or chatop):  # No description provided
        await message.reply_text(
            "Provide a description, like <pre>/nsfw anthro mouse getting vored</pre>",
            parse_mode=ParseMode.HTML,
        )
        return
    if len(parts) > 1:
        description = parts[1] + " " + description

    await do_nsfw_post(context.bot, move_message, description)
    await move_message.delete()


async def replace_invite_link(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Bot /newlink callback
    Replaces bot's invite link for {invite_chat}
    NOTE: Each admin has a DIFFERENT INVITE LINK."""

    if not update.effective_chat or not update.effective_user or not update.message:
        raise AttributeError("Missing required attributes")

    if update.effective_chat.id != admin_chat_id:
        await update.message.reply_text("Unauthorized")
        return

    logging.info(
        "%s (%s) requested invite link rotation",
        update.effective_user.name,
        update.effective_user.id,
    )
    try:
        bot_join_link = await context.bot.export_chat_invite_link(invite_chat_id)
        if bot_join_link is None:
            raise Exception("exportChatInviteLink returned None")
    except Exception as e:
        logging.error("Invite link rotation failed: %s", e)
        await update.message.reply_text("Invite link rotation failed: " + str(e))
        return
    global join_link
    join_link = bot_join_link
    logging.info("New bot invite link: %s", join_link)
    await update.message.reply_text(
        "Success. Bot's new invite link: " + join_link, disable_web_page_preview=True
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot button callback"""

    if (
        not update.message
        or not update.callback_query
        or not update.callback_query.data
    ):
        raise AttributeError("Missing required attributes")

    data = update.callback_query.data

    # Delete own message button
    if data.startswith("d"):
        # action, chat_id, user_id, message_id, requested = data.split(",", 4)
        await update.message.reply_text(
            "Deleting your own posts is not yet implemented, sorry"
        )
        return

    logging.error("Button didn't understand callback: %s", data)


async def version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot /version callback
    Posts bot info and Cloud Function version"""

    if not update.effective_chat:
        raise AttributeError("Missing required attributes")

    await update.effective_chat.send_message(
        "<a href='https://github.com/xbnstudios/furcast-porn-bot'>furcast-porn-bot</a>",
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


async def do_nsfw_post(bot: Bot, media_message: Message, description_html: str) -> None:
    """Create the posts in both main and AD"""

    if not media_message.from_user:
        raise AttributeError("Missing required attributes")

    # Porn chat media forward
    try:
        post = await bot.forward_message(
            porn_chat_id, media_message.chat_id, media_message.message_id
        )
    except telegram.error.BadRequest as e:
        logging.warning(
            "Error forwarding post. Is the bot admin in the main group? "
            "Tried to forward %s - %s",
            media_message.link,
            e,
        )
        return

    # Main chat link post
    mention = "<a href='tg://user?id={}'>{}</a>".format(
        media_message.from_user.id,
        escape(media_message.from_user.first_name),
    )
    main_group_message = await bot.send_message(
        main_chat_id,
        (
            "{mention} shared:\n{description}\n"
            "<a href='{bot}'>Join/post</a>  ⚠️  <a href='{link}'>View NSFW</a>"
        ).format(
            mention=mention,
            link=post.link,
            bot=f"https://t.me/{bot.username}",
            description=description_html,
        ),
        parse_mode=ParseMode.HTML,
        disable_notification=True,
        disable_web_page_preview=True,
    )

    # Porn chat description post
    await bot.send_message(
        porn_chat_id,
        "Shared by {} (<a href='{}'>context</a>) with description:\n{}".format(
            mention, main_group_message.link, description_html
        ),
        parse_mode=ParseMode.HTML,
        disable_notification=True,
        disable_web_page_preview=True,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.exception("Exception while handling an update:", exc_info=context.error)

    if isinstance(update, Update) and update.message:
        await update.message.reply_html(
            "Sorry, something isn't working. The error has been noted, please try again later."
        )

    admin_id = os.environ["BOT_ADMIN"]
    if admin_id is None:
        logging.warning("BOT_ADMIN unset, error notifications unavailable")
        return

    tb_list = traceback.format_exception(
        None, context.error, getattr(context.error, "__traceback__")
    )
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    messages = [
        "Traceback:\n<pre>{}</pre>".format(escape(tb_string)),
        "Update:\n<pre>{}</pre>".format(
            escape(json_dumps(update_str, indent=2, ensure_ascii=False))
        ),
        "Chat:\n<pre>{}</pre>".format(escape(str(context.chat_data))),
        "User:\n<pre>{}</pre>".format(escape(str(context.user_data))),
    ]

    notified = False
    for message in messages:
        await context.bot.send_message(
            admin_id, message, parse_mode=ParseMode.HTML, disable_notification=notified
        )
        notified = True


async def setup(application: Application):
    # Get current bot invite link
    try:
        chat = await application.bot.get_chat(invite_chat_id)
        bot_join_link = chat.invite_link
    except Exception as e:
        logging.info("Failed to get invite link: %s", e)
        bot_join_link = None

    if bot_join_link is None:
        logging.info("Generating new bot invite link...")
        try:
            bot_join_link = await application.bot.export_chat_invite_link(
                invite_chat_id
            )
        except Exception as e:  # Probably no rights
            logging.warning("Unable to generate bot invite link: %s", e)
            pass
    if bot_join_link is not None:
        global join_link
        join_link = bot_join_link


def main():
    application = (
        Application.builder()
        .post_init(setup)
        .token(os.environ["TELEGRAM_TOKEN"])
        .build()
    )

    application.add_error_handler(error_handler)
    application.add_handlers(
        [
            CommandHandler(
                "newlink", replace_invite_link, ~filters.UpdateType.EDITED_MESSAGE
            ),
            CommandHandler("nsfw", nsfw, filters.ChatType.GROUPS),  # supports edits
            CommandHandler("start", start, pm_nonedit),
            CommandHandler("version", version, ~filters.UpdateType.EDITED_MESSAGE),
            CallbackQueryHandler(button),
            post_handler,
        ]
    )

    application.run_polling()


if __name__ == "__main__":
    main()
