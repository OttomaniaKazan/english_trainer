""" Основной файл для работы телеграмм бота """

import re

from telebot import types
from telebot.types import Message

from bot.bot_handlers import create_category_list, create_user, delete_word_by_id, generate_next_card, get_categories_with_duplicate_word, get_last_added_word, get_user_state, not_enough_words, save_word_pair, update_user_state, filter_words_for_user, create_data_for_train, check_pair_duplicate
from bot.buttons import Command
from bot.states import State
from bot.init_bot import bot

user_training_context = {}

@bot.message_handler(commands=['start'])
def start_trainer(message):
    """ Начало тренировки/стартовое меню """

    create_user(message)
    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(types.KeyboardButton("Выбрать категорию"))
    markup.add(types.KeyboardButton("Посмотреть прогресс"))

    bot.send_message(message.chat.id,
                     text="Добро пожаловать в English Trainer",
                     reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Выбрать категорию")
def choose_category(message: Message):
    """ Обработка нажатия на кнопку 'Выбрать категорию' """

    update_user_state(message.from_user.id, State.AWAITING_CATEGORY_SELECTION) # type: ignore
    all_categories = create_category_list(message.from_user.id) # type: ignore

    markup = types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True)

    buttons = []
    learned_buttons = []
    for category in all_categories:
        if category['learned'] == category['total']:
            text = f"{category['name']} (выучена!)"
            learned_buttons.append(types.KeyboardButton(text))
        else:
            text = f'{category['name']} ({category['learned']}/{category['total']})'
            buttons.append(types.KeyboardButton(text))

    markup.add(*buttons, *learned_buttons)

    bot.send_message(message.chat.id,
                     text="Выберите категорию",
                     reply_markup=markup)

@bot.message_handler(func=lambda message: message.text)
def training_words(message):
    user_id = message.from_user.id
    text = message.text.strip()

    # 1. Гарантированная инициализация контекста
    if user_id not in user_training_context:
        user_training_context[user_id] = {}
    context = user_training_context[user_id]

    # 2. Чтение актуального состояния
    current_state = get_user_state(user_id)

    # ==================== СОСТОЯНИЯ ВВОДА ====================
    if current_state == State.WAITING_FOR_RU_WORD:
        if not text:
            bot.send_message(message.chat.id, "Введите слово на русском языке:")
            return
        if not re.match(r'^[А-ЯЁ][а-яё\s]+$', text):
            bot.send_message(message.chat.id, "Формат: первая буква заглавная, только кириллица и пробелы:")
            return

        categories = get_categories_with_duplicate_word(text, user_id)
        if not categories:
            context['temp_ru_word'] = text
            update_user_state(user_id, State.WAITING_FOR_EN_WORD)
            bot.send_message(message.chat.id, f"Введите перевод на английском для '{text}':")
        else:
            context['temp_ru_word'] = text
            update_user_state(user_id, State.WAITING_FOR_CONFIRMATION)
            markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            markup.add(types.KeyboardButton('Да'), types.KeyboardButton('Нет'))
            bot.send_message(
                message.chat.id,
                f"Слово уже есть в категориях: {', '.join(categories)}.\nДобавить в текущую?",
                reply_markup=markup
            )
        return

    if current_state == State.WAITING_FOR_CONFIRMATION:
        if text.lower() in ('да', 'yes'):
            update_user_state(user_id, State.WAITING_FOR_EN_WORD)
            bot.send_message(message.chat.id, f"Введите перевод для '{context.get('temp_ru_word')}':")
        elif text.lower() in ('нет', 'no'):
            context.pop('temp_ru_word', None)
            update_user_state(user_id, State.TRAINING)
            bot.send_message(message.chat.id, "Добавление отменено. Возвращаемся к тренировке.")
        else:
            bot.send_message(message.chat.id, "Выберите 'Да' или 'Нет'.")
        return

    if current_state == State.WAITING_FOR_EN_WORD:
        if not text:
            bot.send_message(message.chat.id, "Введите перевод на английском:")
            return
        if not re.match(r'^[A-Za-z\s]+$', text):
            bot.send_message(message.chat.id, "Перевод должен содержать только латиницу и пробелы:")
            return

        ru_word = context.get('temp_ru_word')
        category = context.get('category_name')

        if check_pair_duplicate(ru_word, text, category, user_id):
            bot.send_message(message.chat.id, f"Пара '{ru_word} — {text}' уже есть в категории '{category}'.")
        else:
            save_word_pair(ru_word, text, category, user_id)
            bot.send_message(message.chat.id, "✅ Слово успешно добавлено!")

            # Обновляем локальный пул
            new_word = get_last_added_word(user_id, category)
            if new_word and 'words_pool' in context:
                context['words_pool'].append(new_word)

        context.pop('temp_ru_word', None)
        update_user_state(user_id, State.TRAINING)
        # После добавления сразу продолжаем тренировку
        generate_next_card(message, user_id, context)
        return

    if current_state == State.WAITING_FOR_DELETE_CONFIRM:
        target = context.get('target_delete_word')
        if text.lower() in ('да', 'yes') and target:
            delete_word_by_id(target['id'], user_id)
            # Удаляем из локального пула
            context['words_pool'] = [w for w in context.get('words_pool', []) if w.word_id != target['id']]
            context.pop('target_delete_word', None)
            update_user_state(user_id, State.TRAINING)
            bot.send_message(message.chat.id, f"Слово '{target['ru']}' удалено.")

            if len(context.get('words_pool', [])) < 4:
                not_enough_words(message)
            else:
                generate_next_card(message, user_id, context, skip_feedback=True)
        elif text.lower() in ('нет', 'no'):
            context.pop('target_delete_word', None)
            update_user_state(user_id, State.TRAINING)
            bot.send_message(message.chat.id, "Удаление отменено.")
        else:
            bot.send_message(message.chat.id, "Выберите 'Да' или 'Нет'.")
        return

    # ==================== РЕЖИМ ТРЕНИРОВКИ ====================
    if current_state == State.TRAINING:
        # 1. Кнопка "Добавить слово"
        if text == Command.ADD_WORD:
            update_user_state(user_id, State.WAITING_FOR_RU_WORD)
            bot.send_message(message.chat.id, "Введите слово на русском языке:")
            return

        # 2. Кнопка "Удалить слово"
        if text == Command.DELETE_WORD:
            word_id = context.get('current_word_id')
            if not word_id:
                bot.send_message(message.chat.id, "Нет активного слова для удаления.")
                return
            context['target_delete_word'] = {
                'id': word_id,
                'ru': context.get('last_ru_word'),
                'en': context.get('correct_en_word')
            }
            update_user_state(user_id, State.WAITING_FOR_DELETE_CONFIRM)
            markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            markup.add(types.KeyboardButton('Да'), types.KeyboardButton('Нет'))
            bot.send_message(message.chat.id, f"Удалить '{context['target_delete_word']['ru']}'?", reply_markup=markup)
            return

        # 3. Кнопка "Дальше"
        if text == Command.NEXT:
            generate_next_card(message, user_id, context, skip_feedback=True)
            return

        # 4. Ответ пользователя на викторину
        correct = (context.get('correct_en_word') or '').strip().lower()
        user_ans = text.strip().lower()

        if user_ans == correct:
            bot.send_message(message.chat.id, "✅ Верно!")
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка. Правильный ответ: {context.get('correct_en_word')}")

        generate_next_card(message, user_id, context)
        return

    # ==================== ПЕРВЫЙ ЗАПУСК / ВЫБОР КАТЕГОРИИ ====================
    update_user_state(user_id, State.TRAINING)
    category_name = text.split(' (')[0].strip()
    words = filter_words_for_user(user_id, category_name)
    context['category_name'] = category_name
    context['words_pool'] = words

    if len(words) < 4:
        not_enough_words(message)
        return

    generate_next_card(message, user_id, context)