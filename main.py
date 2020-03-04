#!/usr/bin/env python3

from datetime import timedelta
from dotenv import load_dotenv
from flask import make_response, Request
from html import escape
import logging
import os
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
from telegram.utils.helpers import escape_markdown

load_dotenv()
if "TELEGRAM_TOKEN" not in os.environ or "APIKEY" not in os.environ:
    logging.error("You forgot to set one of the environment vars!")
    exit(3)

# Parsed as HTML - be sure to escape anything you put in!
join_template = (
    "Hello, {escaped_fname}! The "
    "<a href='https://furcast.fm/chat/#rules'>rules</a> still apply for "
    "content posted via this bot! Just send me media to post. "
    "Your channel invite link is below."
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
    updater = Updater(token=os.environ["TELEGRAM_TOKEN"], use_context=True)
    dispatcher = updater.dispatcher
else:  # Webhook bot
    bot = Bot(token=os.environ["TELEGRAM_TOKEN"])
    dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

POST_MEDIA, POST_DESCRIPTION = range(2)


def post_cancel(update: Update, context: CallbackContext) -> None:
    del context.user_data["media"]
    update.message.reply_text("Cancelled")
    return ConversationHandler.END


def post_description(update: Update, context: CallbackContext) -> None:
    # Porn chat media forward
    post = context.bot.forward_message(
        porn_chat, update.effective_chat.id, context.user_data["media"]
    )

    # Main chat link post
    mention = "[{}](tg://user?id={})".format(
        escape_markdown(update.effective_user.first_name), update.effective_user.id
    )
    main_group_message = context.bot.send_message(
        main_chat,
        (
            "{mention} shared: {description}\n"
            "[Join/post]({bot})  ⚠️  [View NSFW]({link})"
        ).format(
            mention=mention,
            link=post.link,
            bot=f"https://t.me/{context.bot.username}",
            description=update.message.text_markdown,
        ),
        # "Shared by {}, DM me to join. Description: {}".format(
        #    mention, update.message.text_markdown
        # ),
        # reply_markup=InlineKeyboardMarkup(
        #    [
        #        [
        #            InlineKeyboardButton(
        #                text="Join AD Channel",
        #                url=f"https://t.me/{context.bot.username}",
        #            ),
        #            InlineKeyboardButton(text="View NSFW", url=post.link),
        #        ]
        #    ]
        # ),
        parse_mode=ParseMode.MARKDOWN,
        disable_notification=True,
        disable_web_page_preview=True,
    )

    # Porn chat description post
    context.bot.send_message(
        porn_chat,
        "Shared by {} ([context]({})) with description:\n{}".format(
            mention, main_group_message.link, update.message.text_markdown
        ),
        parse_mode=ParseMode.MARKDOWN,
        disable_notification=True,
        disable_web_page_preview=True,
    )
    del context.user_data["media"]
    update.message.reply_text("Thanks, posted!")
    return ConversationHandler.END


def post_description_error(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Sorry, descriptions must be text. Send a text description, or /cancel"
    )
    return POST_DESCRIPTION


def post_media(update: Update, context: CallbackContext) -> None:
    context.user_data["media"] = update.message.message_id
    update.message.reply_text(
        "Cool, now briefly describe what you sent, notably with any "
        'necessary content warnings - e.g. "mouse getting vored". '
        "You can also /cancel"
    )
    return POST_DESCRIPTION


def post_media_error(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "Hi, I help you share NSFW content. This system is meant for media, "
        "which I didn't see in what you sent. If I forgot what we were "
        "talking about, try again. If you need an invite link to the NSFW "
        "channel, say /start. If you think this is a bug, contact the admins."
    )
    return ConversationHandler.END


def post_post(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Just send me the media you want to share!")
    return POST_MEDIA


def post_timeout(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Sorry, your last post timed out, try again.")
    return ConversationHandler.END


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
        # CommandHandler("post", post_post, filters=Filters.private),
        MessageHandler(Filters.private & media_filters, post_media),
        MessageHandler(
            Filters.private & InvertedFilter(media_filters), post_media_error
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
        "[furcast-porn-bot](https://git.xbn.fm/xbn/furcast-porn-bot)\n"
        "GCF version: {}".format(os.environ.get("X_GOOGLE_FUNCTION_VERSION")),
        disable_web_page_preview=True,
        parse_mode=ParseMode.MARKDOWN,
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
