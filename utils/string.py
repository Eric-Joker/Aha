from re import compile


def get_byte_length(s: str, encoding="gbk"):
    return len(s.encode(encoding))


def convert_char(char):
    # 处理半角字符
    if (code := ord(char)) == 0x20:  # 空格
        return chr(0x3000)
    elif 0x21 <= code <= 0x7E:
        return chr(code + 0xFEE0)
    # 处理全角字符
    elif code == 0x3000:  # 空格
        return chr(0x20)
    elif 0xFF01 <= code <= 0xFF5E:
        return chr(code - 0xFEE0)
    return char


def convert_text(text):
    return "".join(convert_char(c) for c in text)


# region aha code
def escape_aha(text: str):
    """转义 Aha 码中的少数特殊字符为 HTML 实体"""
    return text.translate(str.maketrans({"&": "&amp;", "[": "&#91;", "]": "&#93;", ",": "&#44;"}))


def unescape_aha(text: str):
    """反转义 Aha 码"""
    return text.replace("&amp;", "&").replace("&#91;", "[").replace("&#93;", "]").replace("&#44;", ",")


AHA_CODE_PATTERN = compile(r"\[Aha:([^,\]]+)(?:,([^\]]+))?\]")


def parse_aha_code(string, pattern = AHA_CODE_PATTERN):
    """将 Aha 码字符串解析为消息数组"""
    from models.msg import MessageChain

    chain = MessageChain()
    last_pos = 0
    # 遍历所有匹配的 Aha 码
    for match in pattern.finditer(string):
        # 处理 Aha 码之前的文本
        if text_before := string[last_pos : match.start()]:
            chain.append(unescape_aha(text_before))

        # 解析 Aha 码参数
        params = {}
        for param in (match[2] or "").split(","):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = unescape_aha(value)

        chain.append(MessageChain.get_seg_class(match[1])(**params))
        last_pos = match.end()

    # 处理最后一个 Aha 码之后的文本
    if text_after := string[last_pos:]:
        chain.append(unescape_aha(text_after))

    return chain


# endregion
