import sys
from pathlib import Path
from pypinyin import lazy_pinyin
from re import compile, sub


def tokenize(s):
    tokens = []
    i = 0
    while i < len(s):
        if (ch := s[i]).isdigit():
            j = i
            while j < len(s) and s[j].isdigit():
                j += 1
            tokens.append((1, int(s[i:j])))  # 数字类型=1
            i = j
        else:
            # 非数字字符
            if "\u4e00" <= ch <= "\u9fff":  # 汉字
                tokens.append((0, lazy_pinyin(ch)[0]))  # 汉字类型，值用拼音
            elif ch.isalpha():
                tokens.append((2, ch.lower()))  # 字母类型，值小写
            else:
                tokens.append((3, ch))  # 其他类型
            i += 1
    return tokens


def process(target_dir: str):
    if not (base_path := (script_dir := Path(__file__).parent) / target_dir).is_dir():
        print(f"错误：目录 '{base_path}' 不存在")
        sys.exit(1)

    title_pattern = compile(r"^(\s*)(#{1,6})(\s+.*)")
    (md_files := list(base_path.rglob("*.md"))).remove(base_path / "README.md")
    md_files.sort(key=lambda p: (len((rel := p.relative_to(base_path)).parents), tokenize(str(rel))))
    with open(script_dir / "LLM.md", "w", encoding="utf-8") as out_f:
        for md in md_files:
            # 写入文件标题
            out_f.write(f"# File: {md.relative_to(base_path).as_posix()}\n\n")
            last_was_empty = True
            in_code_block = False
            in_comment = False

            with open(md, "r", encoding="utf-8") as in_f:
                for line in in_f:
                    original_line = line
                    line = line.rstrip("\n")

                    # 处理代码块标记
                    if line.lstrip().startswith("```"):
                        out_f.write(original_line)
                        in_code_block = not in_code_block
                        last_was_empty = False
                        continue

                    if in_code_block:
                        out_f.write(original_line)
                        last_was_empty = line.strip() == ""
                        continue

                    # 非代码块，处理注释
                    parts = []
                    remaining = line
                    while remaining:
                        if in_comment:
                            if "-->" in remaining:
                                in_comment = False
                                remaining = remaining[remaining.find("-->") + 3 :]
                            else:
                                remaining = ""  # 注释未结束，跳过整行
                        elif "<!--" in remaining:
                            if (new_remaining := sub(r"<!--.*?-->", "", remaining)) == remaining:
                                if prefix := remaining[: remaining.find("<!--")]:
                                    parts.append(prefix)
                                in_comment = True
                                remaining = ""
                            else:
                                # 单行闭合
                                remaining = new_remaining
                        else:
                            # 无注释
                            parts.append(remaining)
                            remaining = ""

                    if (final_line := "".join(parts)).strip() == "":
                        # 空行压缩
                        if not last_was_empty:
                            out_f.write(final_line + "\n")
                            last_was_empty = True
                    else:
                        # 标题升级
                        if match := title_pattern.match(final_line):
                            final_line = f"{match[1]}#{match[2]}{match[3]}"
                        out_f.write(final_line + "\n")
                        last_was_empty = False

            # 文件末尾添加空行（如果最后不是空行）
            if not last_was_empty:
                out_f.write("\n")


if __name__ == "__main__":
    process(sys.argv[1] if len(sys.argv) > 1 else "zh-CN")
