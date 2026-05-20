from functools import wraps
from datetime import datetime
import os

def users_logger(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Предполагаем, что первый аргумент — это message или user_tg_id
        user_tg_id = args[0] if isinstance(args[0], int) else args[0].from_user.id

        log_file = 'users.log'
        user_exists = False

        # Проверяем, есть ли уже запись об этом пользователе
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if f"user_tg_id: {user_tg_id}" in content:
                    user_exists = True

        # Если пользователя ещё нет в логе — записываем
        if not user_exists:
            with open(log_file, 'a', encoding='utf-8') as f:
                now = datetime.now()
                f.write(f'Дата создания нового пользователя: {now.date()} {now.strftime("%H:%M:%S")}\n')
                f.write(f'Пользователь: , user_tg_id: {user_tg_id}\n')

        # Выполняем оригинальную функцию
        return func(*args, **kwargs)

    return wrapper