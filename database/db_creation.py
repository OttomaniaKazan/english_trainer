""" Модуль создания базы данных """

import os
from dotenv import load_dotenv
from sqlalchemy import text
import sqlalchemy as sq

load_dotenv()

user = os.getenv('DB_USER')
password = os.getenv('DB_PASSWORD')
db_name = os.getenv('DEFAULT_DB')
host = os.getenv('DB_HOST')
port = os.getenv('DB_PORT')
en_ru_db = os.getenv('DB_NAME')

def connect_to_default_db() -> sq.Engine:
    """ Подключение к базе данных по умолчанию, для дальнейшего создания целевой БД """

    DSN = f'postgresql+psycopg://{user}:{password}@{host}:{port}/{db_name}'
    engine = sq.create_engine(DSN)
    print('Подключение к базе данных по умолчанию установлено')
    return engine

def create_en_ru_db(engine: sq.Engine) -> None:
    """ Создание целевой базы данных """

    with engine.connect() as conn:
        conn.execution_options(isolation_level='AUTOCOMMIT')
        result = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{en_ru_db}'"))
        db_exist = result.scalar()

        if not db_exist:
            print(f"База '{en_ru_db}' не найдена.")
            conn.execute(text(f'CREATE DATABASE "{en_ru_db}"'))
            print("База успешно создана!")
        else:
            print("База уже существует.")