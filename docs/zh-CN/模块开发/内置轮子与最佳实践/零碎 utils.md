## `utils.aha`

一些面向 Aha 的工具。

### `at_or_str`

返回一个可以匹配@或纯字符串的正则表达式，拥有一个捕获组。

具有一个参数，传参后只匹配指定 user_id。

### `get_card_by_event`

获取 [Message](../../数据结构/事件对象.md#message) 事件来源者的群名片，不存在时返回其账号昵称。

### `post_msg_to_supers`

向所有 `Super` 权限的用户发送消息。

### `escape_aha` / `unescape_aha`

将在 Aha 码存在特殊意义的字符转义/反转义为 HTML 实体。

### `AHA_CODE_PATTERN`

re.Pattern 实例，可匹配 Aha 码。

### `parse_aha_code`

将包含 Aha 码的字符串解析为消息序列。

## `utils.network`

### `get_httpx_client`

用于全进程尽可能共用一个 `httpx.AsyncClient` 实例。

### `local_srv`

判断字符串是否为本地服务地址。

## `utils.typekit`

类型转换相关。

### `decimal_to_str`

将 `Decimal` 转换为字符串。

## `utils.misc`

### `get_item_by_index`

通过位置索引从字典获取键值，返回元组。

### `round_decimal`

四舍五入 `Decimal` 到指定小数位。

### `find_first_instance`

在序列中查找第一个指定类型元素，允许指定开始与终止位置。返回一个元组，第一个元素为索引，第二个元素为元素本身。

### `is_subsequence`

判断一个序列是否为另一个序列的子序列。

### `is_prefix`

适用于所有序列的 `str.startswith`。

### `is_suffix`

适用于所有序列的 `str.endswith`。

## `utils.playwright`

### `capture_element`

通过 CSS 选择器截图某个元素。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| url | str | 要截图的网页地址。 |
| selector | str | CSS 选择器。 |
| save | PathLike | 保存路径，未提供时向 [文件缓存服务](./文件缓存.md) 注册并随机生成，为 `False` 时不保存为文件。 |
| wait_until | Literal["commit", "domcontentloaded", "load", "networkidle"] | 页面加载完毕判定标准。 |
| return_bytes | bool | 是否返回 bytes。 |

## `utils.aio`
异步相关。

### `async_run_func`

通过 `inspect.iscoroutinefunction` 判断后执行 Callable。如果是同步函数则立刻阻塞执行。

### `async_all`

`all` 的用于异步迭代器的版本。

### `async_any`

`any` 的用于异步迭代器的版本。

### `AsyncCounter`

一个同步上下文管理器，实例化后可通过 `wait_until_zero` 异步方法等待计数器归零。

### `AsyncTee`

用于分叉异步迭代器。

```python
gen1, gen2 = AsyncTee.gen(AsyncIterator())
```

### `run_with_uvloop`

如果安装了 [`uvloop`](https://github.com/MagicStack/uvloop)，则使用其启动 `asyncio` 异步事件循环，否则使用默认启动。

### `try_get_loop`

尝试获取当前正在运行的异步事件循环，若不存在返回 `None`。

### `run_in_executor_else_direct`

如果存在正在运行的事件循环，则使用 `loop.run_in_executor` 执行 Callable，否则直接执行。

### `AsyncConnection`

`multiprocessing.Connection` 或 `multiprocessing.PipeConnection` 的包装器，实现异步方法。

## `utils.string`

### `InlineStr`

通过类方法 `from_iterable` 将迭代器的所有元素拼接成一个字符串，并将其中非字符串且非 [`Text`](../../数据结构/消息序列与消息段.md#text) 实例的对象分别替换为一个 [PUA](https://zh.wikipedia.org/wiki/%E7%A7%81%E4%BA%BA%E4%BD%BF%E7%94%A8%E5%8C%BA) 字符。

实例方法 `to_list` 还原上述过程并返回列表。**仅在同一 [Aha 事件](../订阅与发布事件.md)上下文中才可还原！**

该类继承自 `str`，且覆写了绝大多数方法使其返回为 `InlineStr` 实例。若经过操作后变成了普通 `str` 实例，可以通过 `InlineStr(str)` 获取实例。

会伪随机且均匀分配至 137468 个 PUA 码点。

### `charclass_escape`

只转义正则字符集中有特殊含义的字符，需要传入方括号（不包括）之间的整个字符串。

### `asub` / `series_asub`

`re.sub` 的 `repl` 参数接受异步协程的版本。

## `utils.unit`

### `num2chs` / `num2chs10`

将阿拉伯数字转换为简体中文数字描述。

### `parse_size`

从 `https://github.com/xolox/python-humanfriendly` 复制过来的将基于 [IEC 60027-2](https://zh.wikipedia.org/wiki/IEC_60027) 的字节数量描述转化为字节数。

### `chs2sec`

将中文时间段描述转化为秒数。建议使用 [cn2t](https://github.com/WFLing-seaer/cn2t)。

## `utils.apscheduler`

### `TimeTrigger`

实现延时触发。[示例](计划任务.md#使用与示例)

## `utils.sqlalchemy`

仅支持 SQLite 和 postgreSQL。

### `upsert`

返回 Insert 对象。[使用示例](./长效数据.md#示例)

### `insert_ignore`

返回 Insert 对象，使用方法同上。
