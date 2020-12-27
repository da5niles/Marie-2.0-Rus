import html
from io import BytesIO
from typing import Optional, List

from telegram import Message, Update, Bot, User, Chat, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import run_async, CommandHandler, MessageHandler, Filters
from telegram.utils.helpers import mention_html

import tg_bot.modules.sql.global_bans_sql as sql
from tg_bot import dispatcher, OWNER_ID, SUDO_USERS, SUPPORT_USERS, STRICT_GBAN
from tg_bot.modules.helper_funcs.chat_status import user_admin, is_user_admin
from tg_bot.modules.helper_funcs.extraction import extract_user, extract_user_and_text
from tg_bot.modules.helper_funcs.filters import CustomFilters
from tg_bot.modules.helper_funcs.misc import send_to_list
from tg_bot.modules.sql.users_sql import get_all_chats

GBAN_ENFORCE_GROUP = 6

GBAN_ERRORS = {
    "Пользователь является администратором чата",
     "Чат не найден",
     "Недостаточно прав для ограничения / снятия ограничений участника чата",
     "User_not_participant",
     "Peer_id_invalid",
     "Групповой чат отключен",
     "Нужно быть приглашающим пользователя, чтобы исключить его из основной группы",
     "Chat_admin_required",
     "Только создатель основной группы может исключать администраторов группы",
     "Частный канал",
     "Не в чате"
}

UNGBAN_ERRORS = {
    "Пользователь является администратором чата",
     "Чат не найден",
     "Недостаточно прав для ограничения / снятия ограничений участника чата",
     "User_not_participant",
     "Метод доступен только для супергрупп и чатов каналов",
     "Не в чате",
     "Частный канал",
     "Chat_admin_required",
}


@run_async
def gban(bot: Bot, update: Update, args: List[str]):
    message = update.effective_message  # type: Optional[Message]

    user_id, reason = extract_user_and_text(message, args)

    if not user_id:
        message.reply_text("Похоже, вы не имеете в виду пользователя.")
        return

    if int(user_id) in SUDO_USERS:
        message.reply_text("Я шпионю своим глазком ... войну пользователей sudo! Почему вы, ребята, заводите друг друга?")
        return

    if int(user_id) in SUPPORT_USERS:
        message.reply_text("ОООХ кто-то пытается заблокировать пользователя службы поддержки! * берет попкорн *")
        return

    if user_id == bot.id:
        message.reply_text("-_- Так смешно, давай сам, почему бы и нет? Хорошая попытка.")
        return

    try:
        user_chat = bot.get_chat(user_id)
    except BadRequest as excp:
        message.reply_text(excp.message)
        return

    if user_chat.type != 'private':
        message.reply_text("Это не пользователь!")
        return

    if sql.is_user_gbanned(user_id):
        if not reason:
            message.reply_text("Этот пользователь уже заблокирован; Я бы изменил причину, но ты мне не дал...")
            return

        old_reason = sql.update_gban_reason(user_id, user_chat.username or user_chat.first_name, reason)
        if old_reason:
            message.reply_text("Этот пользователь уже заблокирован по следующей причине:\n"
                               "<code>{}</code>\n"
                               "Я пошел и обновил его с вашей новой причиной!".format(html.escape(old_reason)),
                               parse_mode=ParseMode.HTML)
        else:
            message.reply_text("Этот пользователь уже заблокирован, но для него не установлена причина; Я пошел и обновил это!")

        return

    message.reply_text("⚡️ *Snaps the Banhammer* ⚡️")

    banner = update.effective_user  # type: Optional[User]
    send_to_list(bot, SUDO_USERS + SUPPORT_USERS,
                 "<b>Global Ban</b>" \
                 "\n#GBAN" \
                 "\n<b>Сатус:</b> <code>Enforcing</code>" \
                 "\n<b>Супер ащмин:</b> {}" \
                 "\n<b>Пользователь:</b> {}" \
                 "\n<b>ID:</b> <code>{}</code>" \
                 "\n<b>Причина:</b> {}".format(mention_html(banner.id, banner.first_name),
                                              mention_html(user_chat.id, user_chat.first_name), 
                                                           user_chat.id, reason or "нет"), 
                html=True)

    sql.gban_user(user_id, user_chat.username or user_chat.first_name, reason)

    chats = get_all_chats()
    for chat in chats:
        chat_id = chat.chat_id

        # Check if this group has disabled gbans
        if not sql.does_chat_gban(chat_id):
            continue

        try:
            bot.kick_chat_member(chat_id, user_id)
        except BadRequest as excp:
            if excp.message in GBAN_ERRORS:
                pass
            else:
                message.reply_text("Не удалось выполнить gban из-за: {}".format(excp.message))
                send_to_list(bot, SUDO_USERS + SUPPORT_USERS, "Could not gban due to: {}".format(excp.message))
                sql.ungban_user(user_id)
                return
        except TelegramError:
            pass

    send_to_list(bot, SUDO_USERS + SUPPORT_USERS, 
                  "{} был успешно gbanned!".format(mention_html(user_chat.id, user_chat.first_name)),
                html=True)
    message.reply_text("Человек был заблокирован.")


@run_async
def ungban(bot: Bot, update: Update, args: List[str]):
    message = update.effective_message  # type: Optional[Message]

    user_id = extract_user(message, args)
    if not user_id:
        message.reply_text("Похоже, вы не имеете в виду пользователя.")
        return

    user_chat = bot.get_chat(user_id)
    if user_chat.type != 'private':
        message.reply_text("Это не пользователь!")
        return

    if not sql.is_user_gbanned(user_id):
        message.reply_text("Этот пользователь не заблокирован!")
        return

    banner = update.effective_user  # type: Optional[User]

    message.reply_text("Прошу прощения, {}, глобально второй шанс.".format(user_chat.first_name))

    send_to_list(bot, SUDO_USERS + SUPPORT_USERS,
                 "<b>Regression of Global Ban</b>" \
                 "\n#UNGBAN" \
                 "\n<b>Статус:</b> <code>Ceased</code>" \
                 "\n<b>Супер админ:</b> {}" \
                 "\n<b>Пользователь:</b> {}" \
                 "\n<b>ID:</b> <code>{}</code>".format(mention_html(banner.id, banner.first_name),
                                                       mention_html(user_chat.id, user_chat.first_name), 
                                                                    user_chat.id),
                 html=True)

    chats = get_all_chats()
    for chat in chats:
        chat_id = chat.chat_id

        # Check if this group has disabled gbans
        if not sql.does_chat_gban(chat_id):
            continue

        try:
            member = bot.get_chat_member(chat_id, user_id)
            if member.status == 'kicked':
                bot.unban_chat_member(chat_id, user_id)

        except BadRequest as excp:
            if excp.message in UNGBAN_ERRORS:
                pass
            else:
                message.reply_text("Не удалось отменить gban из-за: {}".format(excp.message))
                bot.send_message(OWNER_ID, "Не удалось отменить gban из-за: {}".format(excp.message))
                return
        except TelegramError:
            pass

    sql.ungban_user(user_id)

    send_to_list(bot, SUDO_USERS + SUPPORT_USERS, 
                  "{}  был помилован из Гбана!".format(mention_html(user_chat.id, 
                                                                         user_chat.first_name)),
                  html=True)

    message.reply_text("Этот человек был разблокирован и помилован!")


@run_async
def gbanlist(bot: Bot, update: Update):
    banned_users = sql.get_gban_list()

    if not banned_users:
        update.effective_message.reply_text("Нет пользователей с gban-аккаунтами! Ты добрее, чем я ожидал...")
        return

    banfile = 'Screw these guys.\n'
    for user in banned_users:
        banfile += "[x] {} - {}\n".format(user["name"], user["user_id"])
        if user["reason"]:
            banfile += "Reason: {}\n".format(user["reason"])

    with BytesIO(str.encode(banfile)) as output:
        output.name = "gbanlist.txt"
        update.effective_message.reply_document(document=output, filename="gbanlist.txt",
                                                caption="Вот список пользователей, которые сейчас заблокированы.")


def check_and_ban(update, user_id, should_message=True):
    if sql.is_user_gbanned(user_id):
        update.effective_chat.kick_member(user_id)
        if should_message:
            update.effective_message.reply_text("Это плохой человек, их здесь не должно быть!")


@run_async
def enforce_gban(bot: Bot, update: Update):
    # Not using @restrict handler to avoid spamming - just ignore if cant gban.
    if sql.does_chat_gban(update.effective_chat.id) and update.effective_chat.get_member(bot.id).can_restrict_members:
        user = update.effective_user  # type: Optional[User]
        chat = update.effective_chat  # type: Optional[Chat]
        msg = update.effective_message  # type: Optional[Message]

        if user and not is_user_admin(chat, user.id):
            check_and_ban(update, user.id)

        if msg.new_chat_members:
            new_members = update.effective_message.new_chat_members
            for mem in new_members:
                check_and_ban(update, mem.id)

        if msg.reply_to_message:
            user = msg.reply_to_message.from_user  # type: Optional[User]
            if user and not is_user_admin(chat, user.id):
                check_and_ban(update, user.id, should_message=False)


@run_async
@user_admin
def gbanstat(bot: Bot, update: Update, args: List[str]):
    if len(args) > 0:
        if args[0].lower() in ["on", "yes"]:
            sql.enable_gbans(update.effective_chat.id)
            update.effective_message.reply_text("Я включил gbans в этой группе. Это поможет защитить вас "
                                                 "от спамеров, сомнительных персонажей и самых больших троллей.")
        elif args[0].lower() in ["off", "no"]:
            sql.disable_gbans(update.effective_chat.id)
            update.effective_message.reply_text("Я отключил gbans в этой группе. GBans не повлияет на ваших пользователей "
                                                 "больше. Вы будете менее защищены от троллей и спамеров"
                                                 "хотя!")
    else:
        update.effective_message.reply_text("Приведите аргументы в пользу выбора настройки! вкл / выкл, да / нет! \n \n "
                                             "Ваша текущая настройка: {} \n"
                                             "Когда True, любые gbans, которые происходят, будут происходить и в вашей группе"
                                             "Когда ложно, они не будут, оставляя вас во власти"
                                             "спамеры.".format(sql.does_chat_gban(update.effective_chat.id)))


def __stats__():
    return "{} gbanned users.".format(sql.num_gbanned_users())


def __user_info__(user_id):
    is_gbanned = sql.is_user_gbanned(user_id)

    text = "Globally banned: <b>{}</b>"
    if is_gbanned:
        text = text.format("Yes")
        user = sql.get_gbanned_user(user_id)
        if user.reason:
            text += "\nReason: {}".format(html.escape(user.reason))
    else:
        text = text.format("No")
    return text


def __migrate__(old_chat_id, new_chat_id):
    sql.migrate_chat(old_chat_id, new_chat_id)


def __chat_settings__(chat_id, user_id):
    return "This chat is enforcing *gbans*: `{}`.".format(sql.does_chat_gban(chat_id))


__help__ = """
* Только администратор: *
  - / gbanstat <on / off / yes / no>: отключит эффект глобальных запретов на вашу группу или вернет ваши текущие настройки.

Gbans, также известные как глобальные запреты, используются владельцами ботов для запрета спамеров во всех группах. Это помогает защитить \
вы и ваши группы, удалив спам-потоки как можно быстрее. Их можно отключить для вашей группы, позвонив \
/ gbanstat
"""

__mod_name__ = "Global Bans"

GBAN_HANDLER = CommandHandler("gban", gban, pass_args=True,
                              filters=CustomFilters.sudo_filter | CustomFilters.support_filter)
UNGBAN_HANDLER = CommandHandler("ungban", ungban, pass_args=True,
                                filters=CustomFilters.sudo_filter | CustomFilters.support_filter)
GBAN_LIST = CommandHandler("gbanlist", gbanlist,
                           filters=CustomFilters.sudo_filter | CustomFilters.support_filter)

GBAN_STATUS = CommandHandler("gbanstat", gbanstat, pass_args=True, filters=Filters.group)

GBAN_ENFORCER = MessageHandler(Filters.all & Filters.group, enforce_gban)

dispatcher.add_handler(GBAN_HANDLER)
dispatcher.add_handler(UNGBAN_HANDLER)
dispatcher.add_handler(GBAN_LIST)
dispatcher.add_handler(GBAN_STATUS)

if STRICT_GBAN:  # enforce GBANS if this is set
    dispatcher.add_handler(GBAN_ENFORCER, GBAN_ENFORCE_GROUP)
