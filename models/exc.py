from httpx import HTTPStatusError


class APIException(Exception):
    """请求 API 异常"""

    def __init__(self, err_msg: str, code=-1):
        self.err_msg = err_msg
        self.code = code
        super().__init__(err_msg, code)
        
    def __str__(self):
        from core.i18n import _
        
        return _("api.service.call.error") % {"code": self.code, "msg": self.err_msg}


class APITimeoutError(APIException, TimeoutError):
    """请求 API 超时"""

    def __init__(self):
        from core.i18n import _

        super().__init__(_("api.service.call.timeout"))


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
