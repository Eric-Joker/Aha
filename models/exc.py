from httpx import HTTPStatusError


class APIException(Exception):
    """API 异常"""


# class AhaExprTypeError(TypeError):
#    """表达式元素类型错误"""


class AhaExprFieldDuplicate(RuntimeError):
    """同名表达式字段被重复实例化"""


class UnknownMessageTypeError(TypeError):
    """消息类型错误异常"""


class DatabaseBackupError(Exception):
    """数据库备份异常"""


class ExactlyOneTruthyValueError(ValueError):
    """恰好有一个真值的情况被违反"""


class DownloadFileMsgError(HTTPStatusError):
    """用于 models.msg.Downloadable"""
