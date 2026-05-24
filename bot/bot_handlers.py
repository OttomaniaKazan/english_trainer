""" Модуль обработчиков для бота """

import random

from sqlalchemy import func, case

from init_bot import bot
from database.db_core import engine, Session
from database.models import Users, Words, Category, ActivityJournal, UserProgress
from bot.states import State
from decorators.decorators import users_logger
from telebot import types
from bot.buttons import Command

from telebot.types import Message
from datetime import datetime

def get_tg_user_id(message: Message) -> int:
    """ Получение ID пользователя Telegram """
    return message.from_user.id # type: ignore

@users_logger
def create_user(message: Message) -> None:
    """ Создание пользователя """

    user_tg_id = get_tg_user_id(message)
    date = datetime.now()

    with Session() as session:
        user = session.query(Users).filter(Users.user_tg_id == user_tg_id).first()
        if not user:
            user = Users(user_tg_id=user_tg_id,
                         created_at=date,
                         state=State.MAIN_MENU)
            session.add(user)
            session.commit()

def get_user_state(user_tg_id: int) -> str:
    """ Получение состояния пользователя """

    with Session() as session:
        user = session.query(Users.state).filter(Users.user_tg_id == user_tg_id).first()
        return user.state if user else State.MAIN_MENU

def not_enough_words(message):
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(types.KeyboardButton(Command.ADD_WORD))
        markup.add(types.KeyboardButton('Выберите категорию'))

        bot.send_message(
            message.chat.id,
            'Недостаточно слов для тренировки в категории!\n' \
            'Выберите действие:',
            reply_markup=markup
        )

def get_categories_with_duplicate_word(ru_word: str, user_tg_id: int) -> list[str] | None:
    """ Поиск категорий, содержащих указанное русское слово (личные + системные, кроме удалённых) """

    cleaned_word = ru_word.strip().lower()
    with Session() as session:
        # Подзапрос идентификаторов слов, удалённых текущим пользователем
        deleted_words = (
            session.query(ActivityJournal.word_id)
            .filter(
                ActivityJournal.user_id == user_tg_id,
                ActivityJournal.action_type == 'delete'
            )
            .distinct()
        )

        categories = (
            session.query(Category.name)
            .join(Words, Category.category_id == Words.category_id)
            .filter(
                (Words.owner_user_id == user_tg_id) | (Words.owner_user_id.is_(None))
            )
            .filter(~Words.word_id.in_(deleted_words))
            .filter(func.lower(func.trim(Words.ru_word)) == cleaned_word)
            .distinct()
            .all()
        )
        result = [row[0] for row in categories]

    return result if result else None


def update_user_state(user_tg_id: int, state: str) -> None:
    """ Обновление состояния пользователя """

    with Session() as session:
        user = session.query(Users).filter(Users.user_tg_id == user_tg_id).first()
        if user:
            user.state = state # type: ignore
            session.commit()

def create_category_list(user_tg_id: int) -> list:
    """ Создание списка категорий """

    with Session() as session:

        # Подзапрос для базового количества слов в каждой категории
        # Это только слова из исходного словаря, без пользовательских добавлений.
        count_base_word = (
            session.query(
                Words.category_id.label('category_id'),
                func.count(Words.word_id).label('base_count')
            )
            .filter(Words.owner_user_id.is_(None))
            .group_by(Words.category_id)
            .subquery()
        )

        # Подзапрос для подсчета добавленных/удаленных слов пользователем
        activity_delta_query = (
            session.query(
                Words.category_id.label('category_id'),
                func.coalesce(
                    func.sum(
                        case(
                            (ActivityJournal.action_type == 'add', 1),
                            (ActivityJournal.action_type == 'delete', -1),
                            else_ = 0
                        )
                    ),
                    0
                ).label('activity_delta')
            )
            .join(ActivityJournal, ActivityJournal.word_id == Words.word_id)
            .filter(ActivityJournal.user_id == user_tg_id)
            .group_by(Words.category_id)
            .subquery()
        )

        # Подзапрос для подсчета выученных слов в каждой категории
        learned_count_query = (
            session.query(
                Words.category_id.label('category_id'),
                func.count(Words.word_id).label('learned_count')
            )
            .join(UserProgress, UserProgress.word_id == Words.word_id)
            .filter(UserProgress.user_tg_id == user_tg_id)
            .filter(UserProgress.is_learned.is_(True))
            .group_by(Words.category_id)
            .subquery()
        )

        # Основной запрос
        categories = (
            session.query(
                Category.category_id,
                Category.name,
                func.coalesce(count_base_word.c.base_count, 0).label('base_count'),
                func.coalesce(activity_delta_query.c.activity_delta, 0).label('activity_delta'),
                func.coalesce(learned_count_query.c.learned_count, 0).label('learned_count'),
            )
            .outerjoin(count_base_word, count_base_word.c.category_id == Category.category_id)
            .outerjoin(activity_delta_query, activity_delta_query.c.category_id == Category.category_id)
            .outerjoin(learned_count_query, learned_count_query.c.category_id == Category.category_id)
            .order_by(learned_count_query.c.learned_count, count_base_word.c.base_count)
            .all()
        )

        category_list = []
        for category in categories:
            total = category.base_count + category.activity_delta
            if total < 0:
                total = 0

            category_list.append({
                'name': category.name,
                'learned': category.learned_count,
                'total': total
            })

    return category_list

def filter_words_for_user(user_tg_id: int, category_name: str) -> list:
    """ Формирование списка слов для тренировки (исключает удалённые и выученные) """
    with Session() as session:
        # Базовый запрос: слова категории (системные + пользовательские)
        base_query = session.query(Words).join(Category).filter(
            Category.name == category_name,
            (Words.owner_user_id.is_(None)) | (Words.owner_user_id == user_tg_id)
        )

        # Подзапрос удалённых слов
        deleted_ids = (
            session.query(Words.word_id)
            .join(Category)
            .join(ActivityJournal, ActivityJournal.word_id == Words.word_id)
            .filter(
                Category.name == category_name,
                ActivityJournal.user_id == user_tg_id,
                ActivityJournal.action_type == 'delete'
            ).distinct()
        )

        # Подзапрос выученных слов
        learned_ids = (
            session.query(UserProgress.word_id)
            .filter(UserProgress.user_tg_id == user_tg_id, UserProgress.is_learned.is_(True))
        )

        return base_query.filter(
            ~Words.word_id.in_(deleted_ids),
            ~Words.word_id.in_(learned_ids)
        ).all()

def create_data_for_train(words: list, previous_ru_word: str | None) -> tuple[str, str, list[str]] | None:
    """ Создание данных для тренировки из списка слов """

    if not words:
        return None

    train_word = random.choice(words)
    ru_word = str(train_word.ru_word)
    for _ in range(15):
        if previous_ru_word and ru_word == previous_ru_word:
            train_word = random.choice(words)
            ru_word = str(train_word.ru_word)
        else:
            break
    en_word = train_word.en_word

    en_words = list({word.en_word for word in words if word.en_word != en_word})

    n_pretendents = min(3, len(en_words))
    if n_pretendents > 0:
        words_pretendents = random.sample(en_words, n_pretendents)
    else:
        words_pretendents = []

    words_pretendents.append(en_word)
    if len(words_pretendents) < 4:
        return None

    random.shuffle(words_pretendents)

    return (ru_word, en_word, words_pretendents)

def check_pair_duplicate(ru_word: str, en_word: str, category_name: str, user_id: int) -> bool:
    """ Проверка: существует ли точная пара в указанной категории (с учётом удалённых) """
    ru_norm = ru_word.strip().lower()
    en_norm = en_word.strip().lower()

    with Session() as session:
        deleted_ids = (
            session.query(ActivityJournal.word_id)
            .filter(ActivityJournal.user_id == user_id, ActivityJournal.action_type == 'delete')
            .distinct()
        )

        exists = (
            session.query(Words.word_id)
            .join(Category, Words.category_id == Category.category_id)
            .filter(
                Category.name == category_name,
                (Words.owner_user_id == user_id) | (Words.owner_user_id.is_(None)),
                func.lower(Words.ru_word) == ru_norm,
                func.lower(Words.en_word) == en_norm,
                ~Words.word_id.in_(deleted_ids)
            )
            .first()
        )
    return exists is not None


def save_word_pair(ru_word: str, en_word: str, category_name: str, user_id: int):
    """ Сохранение слова и логирование добавления """
    with Session() as session:
        category = session.query(Category).filter(Category.name == category_name).first()
        if not category:
            raise ValueError(f"Категория '{category_name}' не найдена")

        new_word = Words(
            ru_word=ru_word,
            en_word=en_word,
            category_id=category.category_id,
            owner_user_id=user_id
        )
        session.add(new_word)
        session.flush()  # Получаем word_id до коммита

        log = ActivityJournal(
            user_id=user_id,
            word_id=new_word.word_id,
            action_type='add',
            created_at=datetime.now()
        )
        session.add(log)
        session.commit()


def get_last_added_word(user_id: int, category_name: str) -> Words | None:
    """ Получение последнего добавленного слова пользователя в категории """
    with Session() as session:
        word = (
            session.query(Words)
            .join(Category, Words.category_id == Category.category_id)
            .filter(
                Words.owner_user_id == user_id,
                Category.name == category_name
            )
            .order_by(Words.word_id.desc())
            .first()
        )
    return word

def delete_word_by_id(word_id: int, user_id: int):
    """ Логирование удаления слова """
    with Session() as session:
        log = ActivityJournal(
            user_id=user_id,
            word_id=word_id,
            action_type='delete',
            created_at=datetime.now()
        )
        session.add(log)
        session.commit()

def generate_next_card(message, user_id, context, skip_feedback=False):
    """ Генерация и отправка следующего вопроса """
    words = context.get('words_pool', [])
    if len(words) < 4:
        not_enough_words(message)
        return

    data = create_data_for_train(words, context.get('last_ru_word'))
    if data is None:
        not_enough_words(message)
        return

    ru_word, correct_en, options = data
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    for opt in options:
        markup.add(types.KeyboardButton(str(opt)))
    markup.add(types.KeyboardButton(Command.ADD_WORD))
    markup.add(types.KeyboardButton(Command.DELETE_WORD))
    markup.add(types.KeyboardButton(Command.NEXT))

    bot.send_message(message.chat.id, f"Как переводится: {ru_word}?", reply_markup=markup)

    # Фиксация состояния для следующего шага
    context.update({
        'last_ru_word': ru_word,
        'correct_en_word': correct_en,
        'current_word_id': next((w.word_id for w in words if w.ru_word == ru_word), None)
    })

def update_word_progress(word_id: int, user_id: int, is_correct: bool) -> bool:
    """
    Обновление прогресса изучения слова.
    Возвращает True, если слово только что перешло в статус 'выучено'.
    """
    with Session() as session:
        progress = session.query(UserProgress).filter_by(
            user_tg_id=user_id, word_id=word_id
        ).first()

        if not progress:
            progress = UserProgress(user_tg_id=user_id, word_id=word_id, correct_streak=0, is_learned=False)
            session.add(progress)

        became_learned = False
        if is_correct:
            progress.correct_streak += 1
            if progress.correct_streak >= 3:
                progress.is_learned = True
                became_learned = True
        else:
            progress.correct_streak = 0
            progress.is_learned = False

        session.commit()
        return became_learned