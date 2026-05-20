"""
Первый запуск и наполнение базы данных
"""

import json
from sqlalchemy.orm import sessionmaker
from pathlib import Path

import database.models
from database.db_core import engine, Base
from database.db_creation import connect_to_default_db, create_en_ru_db
from database.models import Category, Words

def drop_tables() -> None:
    """ Удаление таблиц (для отладки) """

    Base.metadata.drop_all(engine)

def create_tables() -> bool:
    """ Создание таблиц """

    default_engine = connect_to_default_db()
    create_en_ru_db(default_engine)

    # Создание таблиц
    Base.metadata.create_all(engine)
    print("Таблицы созданы")

    Session = sessionmaker(bind=engine)

    with Session() as session:
        data_file = Path(__file__).parent / 'vocabulary.json'

        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

                for category_name, word_dict in data.items():
                    category = Category(name = category_name)
                    session.add(category)
                    session.flush()  # Сохраняем категорию, чтобы получить ее id

                    words_list = [
                        Words(ru_word=ru,
                              en_word=en,
                              category_id=category.category_id,
                              owner_user_id=None)
                              for ru, en in word_dict.items()
                                ]
                    session.add_all(words_list)
                    session.flush()

        except Exception as e:
            print(f"Ошибка при загрузке данных: {e}")
            session.rollback()
            return False

        session.commit()
    return True