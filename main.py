#!/usr/bin/env python3

from __future__ import annotations

from datetime import timedelta
from html import escape
import logging
import os

from dotenv import load_dotenv
from flask import make_response, Request
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    ParseMode,
    Update,
)
import telegram.error
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Dispatcher,
    Filters,
    MessageHandler,
    Updater,
)
from telegram.ext.filters import InvertedFilter

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
    porn_chat = Chats.furcast_nsfw
    main_chat = Chats.furcast
    invite_chat = Chats.furcast_nsfw
    admin_chat = Chats.xbn_chatops
else:
    porn_chat = Chats.riley_test_channel
    main_chat = Chats.riley_test_group
    invite_chat = Chats.riley_test_channel
    admin_chat = Chats.xbn_chatops

join_link = os.environ.get("JOIN_LINK")
apikey = os.environ["APIKEY"]


logging.basicConfig(level=logging.INFO)
if __name__ == "__main__":  # Poll bot
    updater = Updater(token=os.environ["TELEGRAM_TOKEN"])
    dispatcher = updater.dispatcher
else:  # Webhook bot
    bot = Bot(token=os.environ["TELEGRAM_TOKEN"])
    dispatcher = Dispatcher(bot, None, workers=0)

POST_MEDIA, POST_DESCRIPTION = range(2)


def post_cancel(update: Update, context: CallbackContext) -> None:
    logging.debug(
        "post_cancel: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    del context.user_data["media"]
    update.message.reply_text("Cancelled")
    return ConversationHandler.END


def post_description(update: Update, context: CallbackContext) -> None:
    logging.debug(
        "post_description: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    do_nsfw_post(context.bot, context.user_data["media"], update.message.text_html)
    del context.user_data["media"]
    update.message.reply_text("Thanks, posted!")
    return ConversationHandler.END


def post_description_error(update: Update, context: CallbackContext) -> None:
    logging.debug(
        "post_description_error: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    update.message.reply_text(
        "Sorry, descriptions must be text. Send a text description, or /cancel"
    )
    return POST_DESCRIPTION


def post_media(update: Update, context: CallbackContext) -> None:
    logging.debug(
        "post_media: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    context.user_data["media"] = update.message
    update.message.reply_html(
        "Now tell me the <b>content warnings</b> and <b>tags</b>, e.g.\n"
        "• irl sexytimes with my mate\n"
        "• anthro mouse getting vored\n"
        "• fisting cute anthro wolf\n"
        "(or /cancel)"
    )
    return POST_DESCRIPTION


def post_media_error(update: Update, context: CallbackContext) -> None:
    logging.debug(
        "post_media_error: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    update.message.reply_text(
        "Hi, I help you share NSFW content. This system is meant for media, "
        "which I didn't see in what you sent. If I forgot what we were "
        "talking about, try again. If you need an invite link to the NSFW "
        "channel, say /start. If you think this is a bug, contact the admins."
    )
    return ConversationHandler.END


def post_post(update: Update, context: CallbackContext) -> None:
    logging.debug(
        "post_post: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    update.message.reply_text("Just send me the media you want to share!")
    return POST_MEDIA


def post_timeout(update: Update, context: CallbackContext) -> None:
    logging.debug(
        "post_timeout: %s %s",
        update.effective_user.username,
        update.effective_user.id,
    )
    update.message.reply_text("Sorry, your last post timed out, try again.")


media_filters = (
    Filters.entity(MessageEntity.URL)  # Plain URL
    | Filters.entity(MessageEntity.TEXT_LINK)  # Formatted link
    | Filters.animation
    | Filters.audio
    | Filters.document
    | Filters.photo
    | Filters.sticker
    | Filters.video
    | Filters.video_note  # "Telescope" video
    | Filters.voice  # Voice notes
)
post_handler = ConversationHandler(
    entry_points=[
        # CommandHandler("post", post_post, filters=Filters.chat_type.private),
        MessageHandler(Filters.chat_type.private & media_filters, post_media),
        MessageHandler(
            Filters.chat_type.private & InvertedFilter(media_filters), post_media_error
        ),
    ],
    states={
        POST_MEDIA: [
            MessageHandler(media_filters, post_media),
            MessageHandler(InvertedFilter(media_filters), post_media_error),
        ],
        POST_DESCRIPTION: [
            CommandHandler("cancel", post_cancel),
            MessageHandler(Filters.text, post_description),
            MessageHandler(InvertedFilter(Filters.text), post_description_error),
        ],
        ConversationHandler.TIMEOUT: [MessageHandler(Filters.all, post_timeout)],
    },
    fallbacks=[CommandHandler("cancel", post_cancel)],
    conversation_timeout=timedelta(minutes=3),
)


def start(update: Update, context: CallbackContext) -> None:
    """Bot /start callback
    Gives user invite link button"""

    if update.effective_chat.type != "private":
        return
    logging.info(
        "Inviting %s (%s, %s)",
        update.effective_user.username,
        update.effective_user.full_name,
        update.effective_user.id,
    )

    # Make sure user is in the main chat
    try:
        main_chat_user = context.bot.get_chat(main_chat).get_member(
            update.effective_user.id
        )
    except telegram.error.BadRequest as e:
        logging.warning(
            "Error finding user %s (%s): %s",
            update.effective_user.name,
            update.effective_user.id,
            e,
        )
        main_chat_user = None
    if main_chat_user is None or main_chat_user.status not in [
        "member",
        "administrator",
        "creator",
    ]:
        logging.warning(
            "Not inviting %s (%s): %s",
            update.effective_user.name,
            update.effective_user.id,
            main_chat_user,
        )
        update.message.reply_text("Sorry, this bot serves a private group.")
        return

    # Send link
    update.message.reply_html(
        text=join_template.format(
            escaped_fname=escape(update.message.from_user.first_name)
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=button_text, url=join_link)]]
        ),
        disable_web_page_preview=True,
    )


def nsfw(update: Update, context: CallbackContext) -> None:
    """Bot /nsfw callback
    Moves a post to the NSFW channel"""

    if update.effective_chat.id != main_chat:
        update.message.reply_text("Sorry, this command only works in the main chat.")
        return

    move_message = update.message.reply_to_message
    if move_message is None:
        update.message.reply_text(
            "You forgot to reply to the message that needs to be moved!"
        )
        return

    chat_user = context.bot.get_chat(main_chat).get_member(update.effective_user.id)
    chatop = chat_user.can_delete_messages or chat_user.status == "creator"
    if not (
        # This is a stupid hack because MessageFilter|MessageFilter=MergedFilter,
        # which is an UpdateFilter...
        media_filters.filter(Update(0, move_message))
        or chatop
    ):
        update.message.reply_text("Only media can be moved")
        return

    if not (move_message.from_user.id == update.effective_user.id or chatop):
        update.message.reply_text(
            "Sorry, command is for your own messages or admins. "
            "Please @ an admin if someone else's post should be moved."
        )
        return

    parts = update.message.text_html.strip().split(" ", 1)
    description = "(moved from main chat)"
    if not (len(parts) > 1 or chatop):  # No description provided
        update.message.reply_text(
            "Provide a description, like <pre>/nsfw anthro mouse getting vored</pre>",
            parse_mode=ParseMode.HTML,
        )
        return
    if len(parts) > 1:
        description = parts[1] + " " + description

    do_nsfw_post(context.bot, move_message, description)
    move_message.delete()


def replace_invite_link(update: Update, context: CallbackContext) -> None:
    """Bot /newlink callback
    Replaces bot's invite link for {invite_chat}
    NOTE: Each admin has a DIFFERENT INVITE LINK."""

    if update.effective_chat.id != admin_chat:
        update.message.reply_text("Unauthorized")
        return

    logging.info(
        "%s (%s) requested invite link rotation",
        update.effective_user.name,
        update.effective_user.id,
    )
    try:
        bot_join_link = updater.bot.export_chat_invite_link(invite_chat)
        if bot_join_link is None:
            raise Exception("exportChatInviteLink returned None")
    except Exception as e:
        logging.error("Invite link rotation failed: %s", e)
        update.message.reply_text("Invite link rotation failed: " + str(e))
        return
    global join_link
    join_link = bot_join_link
    logging.info("New bot invite link: %s", join_link)
    update.message.reply_text(
        "Success. Bot's new invite link: " + join_link, disable_web_page_preview=True
    )


def button(update: Update, context: CallbackContext) -> None:
    """Bot button callback"""

    data = update.callback_query.data

    # Delete own message button
    if data.startswith("d"):
        action, chat_id, user_id, message_id, requested = data.split(",", 4)
        update.message.reply_text("Not yet implemented")
        return

    logging.error("Button didn't understand callback: %s", data)


def version(update: Update, context: CallbackContext) -> None:
    """Bot /version callback
    Posts bot info and Cloud Function version"""

    update.effective_chat.send_message(
        "<a href='https://github.com/xbnstudios/furcast-porn-bot'>furcast-porn-bot</a>\n"
        "GCF version: {}".format(os.environ.get("X_GOOGLE_FUNCTION_VERSION")),
        disable_web_page_preview=True,
        parse_mode=ParseMode.HTML,
    )


def do_nsfw_post(bot: Bot, media_message: Message, description_html: str) -> None:
    """Create the posts in both main and AD"""

    # Porn chat media forward
    try:
        post = bot.forward_message(
            porn_chat, media_message.chat_id, media_message.message_id
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
    main_group_message = bot.send_message(
        main_chat,
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
    bot.send_message(
        porn_chat,
        "Shared by {} (<a href='{}'>context</a>) with description:\n{}".format(
            mention, main_group_message.link, description_html
        ),
        parse_mode=ParseMode.HTML,
        disable_notification=True,
        disable_web_page_preview=True,
    )


def webhook(request: Request):
    logging.info("access_route: %s", ",".join(request.access_route))
    logging.info("args: %s", request.args)
    logging.info("data: %s", request.data)
    logging.info("form: %s", request.form)
    if request.args.get("apikey") != apikey:
        return make_response("", 404)
    if "version" in request.args:
        return str(os.environ.get("X_GOOGLE_FUNCTION_VERSION")) + "\n"
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)


dispatcher.add_handler(CommandHandler("newlink", replace_invite_link))
dispatcher.add_handler(CommandHandler("nsfw", nsfw))
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("version", version))
dispatcher.add_handler(CallbackQueryHandler(button))
dispatcher.add_handler(post_handler)

if __name__ == "__main__":
    # Get current bot invite link
    try:
        chat = updater.bot.get_chat(invite_chat)
        bot_join_link = chat.invite_link
    except Exception as e:
        logging.info("Failed to get invite link: %s", e)
        bot_join_link = None

    if bot_join_link is None:
        logging.info("Generating new bot invite link...")
        try:
            bot_join_link = updater.bot.export_chat_invite_link(invite_chat)
        except Exception as e:  # Probably no rights
            logging.warning("Unable to generate bot invite link: %s", e)
            pass
    if bot_join_link is not None:
        join_link = bot_join_link

    # Start responding
    updater.start_polling()
    updater.idle()
