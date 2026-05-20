""" Описание таблиц в БД """

import sqlalchemy as sq
from sqlalchemy.orm import relationship
from database.db_core import Base

class Category(Base):
    __tablename__ = 'category'

    category_id = sq.Column(sq.Integer, primary_key=True, autoincrement=True, nullable=False)
    name = sq.Column(sq.String(length=50), nullable=False)

    words = relationship('Words', back_populates='category')

class Users(Base):
    __tablename__ = 'users'

    user_tg_id = sq.Column(sq.BigInteger, primary_key=True, nullable=False)
    created_at = sq.Column(sq.DateTime, nullable=False)
    state = sq.Column(sq.String(length=50), nullable=False)

    words = relationship('Words', back_populates='owner')
    activity_logs = relationship('ActivityJournal', back_populates='user')
    progress = relationship('UserProgress', back_populates='user')

class Words(Base):
    __tablename__ = 'words'

    word_id = sq.Column(sq.Integer, primary_key=True, autoincrement=True, nullable=False)
    ru_word = sq.Column(sq.String(length=200), nullable=False)
    en_word = sq.Column(sq.String(length=200), nullable=False)
    category_id = sq.Column(sq.Integer, sq.ForeignKey('category.category_id'), nullable=False)
    owner_user_id = sq.Column(sq.BigInteger, sq.ForeignKey('users.user_tg_id', ondelete='CASCADE'), nullable=True)

    category = relationship('Category', back_populates='words')
    owner = relationship('Users', back_populates='words')
    activity_logs = relationship('ActivityJournal', back_populates='word')
    progress = relationship('UserProgress', back_populates='word')

class ActivityJournal(Base):
    __tablename__ = 'activity_journal'

    activity_id = sq.Column(sq.Integer, primary_key=True, autoincrement=True, nullable=False)
    action_type = sq.Column(sq.String(length=50), nullable=False)
    word_id = sq.Column(sq.Integer, sq.ForeignKey('words.word_id', ondelete='CASCADE'), nullable=False)
    user_id = sq.Column(sq.BigInteger, sq.ForeignKey('users.user_tg_id', ondelete='CASCADE'), nullable=False)

    word = relationship('Words', back_populates='activity_logs')
    user = relationship('Users', back_populates='activity_logs')

class UserProgress(Base):
    __tablename__ = 'user_progress'

    correct_streak = sq.Column(sq.Integer, default=0)
    is_learned = sq.Column(sq.Boolean, default=False)
    user_tg_id = sq.Column(sq.BigInteger, sq.ForeignKey('users.user_tg_id', ondelete='CASCADE'), nullable=False)
    word_id = sq.Column(sq.Integer, sq.ForeignKey('words.word_id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (sq.PrimaryKeyConstraint('user_tg_id', 'word_id'),)

    user = relationship('Users', back_populates='progress')
    word = relationship("Words", back_populates='progress')