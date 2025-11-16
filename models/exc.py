class APIException(Exception):
    """API 异常"""


#class AhaExprTypeError(TypeError):
#    """表达式元素类型错误"""


class UnknownMessageTypeError(TypeError):
    """消息类型错误异常"""


class ContentNotAccessedError(RuntimeError):
    """在存在上下文数据之前尝试获取上下文时抛出"""


class ExactlyOneTruthyValueError(ValueError):
    """恰好有一个真值的情况被违反"""
