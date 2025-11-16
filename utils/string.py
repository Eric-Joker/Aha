

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


def escape_aha(text: str):
    """转义 Aha 码中的少数特殊字符为 HTML 实体"""
    return text.translate(str.maketrans({"&": "&amp;", "[": "&#91;", "]": "&#93;", ",": "&#44;"}))


def unescape_aha(text: str):
    """反转义 Aha 码"""
    return text.replace("&amp;", "&").replace("&#91;", "[").replace("&#93;", "]").replace("&#44;", ",")
