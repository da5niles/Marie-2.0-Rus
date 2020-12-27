import json
from io import BytesIO
from typing import Optional

from telegram import Message, Chat, Update, Bot
from telegram.error import BadRequest
from telegram.ext import CommandHandler, run_async

from tg_bot import dispatcher, LOGGER
from tg_bot.__main__ import DATA_IMPORT
from tg_bot.modules.helper_funcs.chat_status import user_admin


@run_async
@user_admin
def import_data(bot: Bot, update):
    msg = update.effective_message  # type: Optional[Message]
    chat = update.effective_chat  # type: Optional[Chat]
    # TODO: allow uploading doc with command, not just as reply
    # only work with a doc
    if msg.reply_to_message and msg.reply_to_message.document:
        try:
            file_info = bot.get_file(msg.reply_to_message.document.file_id)
        except BadRequest:
            msg.reply_text("Попробуйте загрузить и повторно загрузить файл как вы перед импортом - кажется, "
                           "быть сомнительным!")
            return

        with BytesIO() as file:
            file_info.download(out=file)
            file.seek(0)
            data = json.load(file)

        # only import one group
        if len(data) > 1 and str(chat.id) not in data:
            msg.reply_text("В этом файле больше одной группы, и ни у одной из них нет такого же идентификатора чата, как у этой группы "
                           "- как выбрать, что импортировать?")
            return

        # Select data source
        if str(chat.id) in data:
            data = data[str(chat.id)]['hashes']
        else:
            data = data[list(data.keys())[0]]['hashes']

        try:
            for mod in DATA_IMPORT:
                mod.__import_data__(str(chat.id), data)
        except Exception:
            msg.reply_text("Исключение при восстановлении ваших данных. Возможно, процесс не завершен. Если "
                            "у вас возникли проблемы с этим, сообщите куда-то там, потом придумаем куда, с файлом резервной копии, чтобы"
                            "проблема может быть устранена. Мои владельцы будут рады помочь, и каждая ошибка"
                            "сообщение делает меня лучше! Спасибо! :)")
            LOGGER.exception("Импорт для чата с ID %s с именем %s не удалось.", str(chat.id), str(chat.title))
            return

        # TODO: some of that link logic
        # NOTE: consider default permissions stuff?
        msg.reply_text("Бэкап полностью импортирован. Добро пожаловать! :D")


@run_async
@user_admin
def export_data(bot: Bot, update: Update):
    msg = update.effective_message  # type: Optional[Message]
    msg.reply_text("")


__mod_name__ = "Бэкап"

__help__ = """
* Только администратор: *
  - /import: ответьте на файл резервной копии группового дворецкого, чтобы импортировать как можно больше, что делает передачу очень простой! Запись \
что файлы / фотографии не могут быть импортированы из-за ограничений телеграммы.
  - /export: !!! Это еще не команда, но скоро она появится!
"""
IMPORT_HANDLER = CommandHandler("import", import_data)
EXPORT_HANDLER = CommandHandler("export", export_data)

dispatcher.add_handler(IMPORT_HANDLER)
# dispatcher.add_handler(EXPORT_HANDLER)
