<div align="center">

[![](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Eric-Joker/Aha/blob/main/LICENSE)
[![](https://img.shields.io/badge/CPython-3.14-yellow)](https://www.python.org)

[🛠安装与使用](./docs/zh-CN/安装与使用.md) |
[📖文档](./docs/zh-CN/README.md) | [💡议题](https://github.com/Eric-Joker/Aha/issues)

</div>

# Aha

Aha 是一个目标为~~跨平台~~、高性能、极为灵活的 Python 聊天机器人后端框架。提供了很多统一、标准化的轮子，为需求实现提供高度自由便捷的支持。

目前本项目还在毛坯期，基本只供我自用，未提供懒人设施，若有需要可以提 issue。

## 特色

- 基于 DSL 的词条匹配系统
  ```python
  from core.expr import Pmsg, Or
  from core.dispatcher import on_message

  @on_message((Pmsg == "绝对匹配") | (Pmsg.fullmatch("正则匹配")))
  # 直接作为 `on_message` 的参数或逻辑运算类的参数时可省略一些字段。
  @on_message("正则匹配")
  ```

- 统一配置系统
  ```python
  # modules/aichat.py
  from core.config import cfg

  LENGTH = cfg.register("max_length", 20, "每个会话最大历史记录数。")
  cfg.max_length  # 以后可如此获取配置
  ```
  会在项目根目录的 config.xxx.yml 中自动生成↓
  ```yaml
  modules.aichat:
    # 每个会话最大历史记录数，必须大于2。
    max_length: 20
  ```

- 国际化支持
  ```python
  from core.i18n import _
  from utils.aha import at_or_str

  @on_message(_("command") % (a := at_or_str(), a), Pprefix == True)
  async def linker(event: Message, localizer):
    return await event.reply(localizer("reply"))  # 返回与触发词条的语言对应的翻译
  ```

- 等等。
