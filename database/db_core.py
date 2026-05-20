""" Модуль настроек подключения к базе данных """

import os
from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

db_name = os.getenv('DB_NAME')
user = os.getenv('DB_USER')
password = os.getenv('DB_PASSWORD')
host = os.getenv('DB_HOST')
port = os.getenv('DB_PORT')

DSN = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db_name}"

engine = create_engine(DSN)
Base = declarative_base()