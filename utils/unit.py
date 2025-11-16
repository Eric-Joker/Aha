import re
from collections import defaultdict, namedtuple
from numbers import Number

SEC_CHS_MAP = (("天", 86400), ("小时", 3600), ("分钟", 60), ("秒", 1))


def sec2chs(seconds: int) -> str:
    parts = []
    for unit, div in SEC_CHS_MAP:
        if value := seconds // div:
            parts.append(f"{value}{unit}")
        seconds %= div
    return "".join(parts) or "0秒"


CHS_NUM_UNITS = ("", "万", "亿", "兆", "京", "垓", "秭", "穰", "沟", "涧", "正", "载", "极")


def num2chs(num: float, threshold: float = 10000) -> str:
    for unit in CHS_NUM_UNITS:
        if num < threshold:
            return f"{num}{unit}"
        num /= 10000
    return f"{num}恒河沙"


CHS_NUM_ORD_UNITS = ("", "十", "百", "千", "万", "十万", "百万", "千万", "亿", "十亿", "百亿", "千亿", "万亿", "十万亿")


def num2chs10(num: float, threshold: float = 10) -> str:
    for unit in CHS_NUM_ORD_UNITS:
        if num < threshold:
            return f"{num}{unit}"
        num /= 10
    return f"{num}百万亿"


# region parse_size by humanfriendly
SizeUnit = namedtuple("SizeUnit", "divider, symbol, name")
CombinedUnit = namedtuple("CombinedUnit", "decimal, binary")
disk_size_units = (
    CombinedUnit(SizeUnit(1000**1, "KB", "kilobyte"), SizeUnit(1024**1, "KiB", "kibibyte")),
    CombinedUnit(SizeUnit(1000**2, "MB", "megabyte"), SizeUnit(1024**2, "MiB", "mebibyte")),
    CombinedUnit(SizeUnit(1000**3, "GB", "gigabyte"), SizeUnit(1024**3, "GiB", "gibibyte")),
    CombinedUnit(SizeUnit(1000**4, "TB", "terabyte"), SizeUnit(1024**4, "TiB", "tebibyte")),
    CombinedUnit(SizeUnit(1000**5, "PB", "petabyte"), SizeUnit(1024**5, "PiB", "pebibyte")),
    CombinedUnit(SizeUnit(1000**6, "EB", "exabyte"), SizeUnit(1024**6, "EiB", "exbibyte")),
    CombinedUnit(SizeUnit(1000**7, "ZB", "zettabyte"), SizeUnit(1024**7, "ZiB", "zebibyte")),
    CombinedUnit(SizeUnit(1000**8, "YB", "yottabyte"), SizeUnit(1024**8, "YiB", "yobibyte")),
)


def tokenize(text):
    tokenized_input = []
    for token in re.split(r"(\d+(?:\.\d+)?)", text):
        if re.match(r"\d+\.\d+", token := token.strip()):
            tokenized_input.append(float(token))
        elif token.isdigit():
            tokenized_input.append(int(token))
        elif token:
            tokenized_input.append(token)
    return tokenized_input


def parse_size(size, binary=False):
    if (tokens := tokenize(size)) and isinstance(tokens[0], Number):
        normalized_unit = tokens[1].lower() if len(tokens) == 2 and isinstance(tokens[1], str) else ""
        if len(tokens) == 1 or normalized_unit.startswith("b"):
            return int(tokens[0])
        if normalized_unit:
            normalized_unit = normalized_unit.rstrip("s")
            for unit in disk_size_units:
                if normalized_unit in (unit.binary.symbol.lower(), unit.binary.name.lower()):
                    return int(tokens[0] * unit.binary.divider)
                if normalized_unit in (unit.decimal.symbol.lower(), unit.decimal.name.lower()) or normalized_unit.startswith(
                    unit.decimal.symbol[0].lower()
                ):
                    return int(tokens[0] * (unit.binary.divider if binary else unit.decimal.divider))
    raise ValueError("Failed to parse size! (input %r was tokenized as %r)" % (size, tokens))


# endregion
# region chs2sec
NUM_PATTERN = re.compile(
    r"(?:([\d\u4e00-\u9fa5a-zA-Z]*?)\s*)"
    r"(?:$|个?(小时|分钟|秒钟|[年个月周天日时分秒刻]|years?|y|mon(?:th)?s?|weeks?|w|days?|d|hours?|h|min(?:ute)?s?|m|sec(?:ond)?s?|s|qtr))",
    re.IGNORECASE,
)

# fmt: off
CHINESE_NUM = {
    '零':0, '一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10,
    '佰':100, '仟':1000, '萬':10000, '亿':100000000,
    '壹':1, '贰':2, '叁':3, '肆':4, '伍':5, '陆':6, '柒':7, '捌':8, '玖':9, '拾':10,
    '两':2, '百':100, '千':1000, '万':10000, '億':100000000, '〇':0,
    '兆':1000000, '桿':1000
} # '廿':20, '卅':30, '卌':40, '卄':20, '卋':30, '皕':200, 

UNIT_MAP = {
    '年':'year', '月':'month', '周':'week', '日':'day', '天':'day', '刻':'quarter',
    '小时':'hour', '时':'hour', '分钟':'minute', '分':'minute', '秒':'second',
    'year':'year', 'years':'year', 'y':'year', 'month':'month', 'months':'month', 'mons':'month', 'mon':'month', 'qtr':'quarter',
    'week':'week', 'weeks':'week', 'w':'week', 'day':'day', 'days':'day', 'd':'day', 'hour':'hour',
    'hours':'hour', 'h':'hour', 'minute':'minute', 'minutes':'minute', 'min':'minute', 'mins':'minute', 'm':'minute',
    'second':'second', 'seconds':'second', 's':'second', 'sec':'second', 'secs':'second'
}

UNIT_SECONDS = {
    'year': 31556952, 'month': 2629746, 'day': 86400, 'hour': 3600,
    'minute': 60, 'second': 1, 'quarter': 788400, 'week': 604800
}

UNIT_ORDER = [
    ['year', 'month', 'day', 'hour', 'minute', 'second'],
    ['month', 'day', 'hour', 'minute', 'second'],
    ['day', 'hour', 'minute', 'second'],
    ['hour', 'minute', 'second'],
    ['minute', 'second'],
    ['second']
]
# fmt: on

CHINESE_NUM_SET = frozenset(CHINESE_NUM)
TIME_STRS = set(CHINESE_NUM).union(UNIT_MAP)


def _chinese_to_int(s: str):
    total = current = 0
    for char in s:
        val = CHINESE_NUM[char]
        if val >= 10:
            current = (current or 1) * val
            # 处理万/亿等大单位
            if val >= 10000:
                total, current = total + current, 0
        else:
            total += current
            current = val
    return total + current


def _parse_number(s: str):
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    return _chinese_to_int(s) if all(c in CHINESE_NUM_SET for c in s) else None


def split_string(s):
    if (n := len(s)) == 0:
        return []

    best_count, best_sep, best_sep_len = 0, None, 0
    for sep_len in range(1, n):
        if (n - 1) // (sep_len + 1) < best_count:
            break

        sep_positions = defaultdict(list)
        for i in range(n - sep_len + 1):
            sep_positions[s[i : i + sep_len]].append(i)

        for sep, positions in sep_positions.items():
            if sep.isdigit() or sep in TIME_STRS:
                continue
            if not (valid := [i for i in positions if 0 < i < n - sep_len]):
                continue

            count, last_pos = 0, -sep_len
            valid.sort()
            for pos in valid:
                if pos >= last_pos + sep_len:
                    segment_start = last_pos + sep_len
                    if pos - segment_start > 0:
                        count += 1
                        last_pos = pos

            total_segments = count + 1 if n - last_pos + sep_len > 0 else count

            if (total_segments > best_count) or (total_segments == best_count and sep_len > best_sep_len):
                best_count = total_segments
                best_sep = sep
                best_sep_len = sep_len

    return [part for part in s.split(best_sep) if part] if best_sep is not None else []


def chs2sec(time_str: str):
    total = prev_end = 0

    for match in NUM_PATTERN.finditer(time_str):
        if not match.group():
            continue

        start, end = match.start(), match.end()
        if start != prev_end:
            break
        prev_end = end

        num_part, unit_part = match.groups()
        num = _parse_number(num_part) if num_part else 1
        if num is None:
            return None

        unit = UNIT_MAP.get(unit_part.lower()) if unit_part else "second"
        if unit is None:
            return None

        if total:
            total += num * UNIT_SECONDS[unit]
        else:
            total = num * UNIT_SECONDS[unit]

    if not total and prev_end != len(time_str):
        parts = []
        for x in split_string(time_str):
            if (part := _parse_number(x)) is None:
                return None
            parts.append(part)
        if 0 < (length := len(parts)) <= 6:
            return sum(part * UNIT_SECONDS[unit] for part, unit in zip(parts, UNIT_ORDER[6 - length]))
        return None

    return total


# endregion
