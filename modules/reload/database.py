from sqlalchemy import Column, String, Integer

from core.database import dbBase


class Status(dbBase):
    __tablename__ = "restart_request"

    bot_id = Column(Integer, default=None)
    platform = Column(String(16), primary_key=True)
    group_id = Column(String(255), default=None, primary_key=True)
    user_id = Column(String(255), primary_key=True)
    message_id = Column(String(255), default=None)
