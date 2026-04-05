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

用于整个进程尽可能共用一个无参数的 `httpx.AsyncClient` 实例。

### `local_srv`

判断字符串是否为本地服务地址。

## `utils.container`

### `find_first_instance`

在序列中查找第一个指定类型元素，允许指定开始与终止位置。返回一个元组，第一个元素为索引，第二个元素为元素本身。

### `is_subsequence`

判断一个序列是否为另一个序列的子序列。

### `is_prefix`

适用于所有序列的 `str.startswith`，第二个参数是否为第一个参数的前缀。

### `is_suffix`

适用于所有序列的 `str.endswith`，第二个参数是否为第一个参数的后缀。

## `utils.misc`

### `get_item_by_index`

通过位置索引从字典获取键值，返回元组。

### `round_decimal`

四舍五入 `Decimal` 到指定小数位。

### `decimal_to_str`

将 `Decimal` 转换为字符串。

## `utils.aio`
异步相关。

### `async_run_func`

先直接执行函数，若返回一个协程则 await 其并返回结果，否则直接返回结果。

### `async_all`

`all` 的用于异步迭代器的版本。

### `async_any`

`any` 的用于异步迭代器的版本。

### `AsyncCounter`

一个同步上下文管理器，实例化后可通过 `wait_until_zero` 异步方法等待计数器归零。

非线程安全。

### `AsyncTee`

用于分叉异步迭代器。

懒得做线程安全。

```python
gen1, gen2 = AsyncTee.gen(AsyncIterator())  # 第二个参数为返回的迭代器数量，默认为 2；第三个参数为缓冲区最大长度，为 0 时不限制，默认为 2。
```

### `run_with_uvloop`

如果安装了 [`uvloop`](https://github.com/MagicStack/uvloop)，则使用其启动 `asyncio` 异步事件循环，否则使用默认启动。

### `try_get_loop`

尝试获取当前正在运行的异步事件循环，若不存在返回 `None`。

### `run_in_executor_else_direct`

如果存在正在运行的事件循环，则使用 `loop.run_in_executor` 执行 Callable，否则直接执行。

## `utils.string`

### `InlineStr`

通过类方法 `from_iterable` 将可迭代对象的**所有元素拼接成一个字符串**，并为其中**非字符串且非 [`Text`](../../数据结构/消息序列与消息段.md#text) 实例**的对象分别**随机分配为一个字符**。分配的字符可能为未分配码点和 [PUA](https://zh.wikipedia.org/wiki/%E7%A7%81%E4%BA%BA%E4%BD%BF%E7%94%A8%E5%8C%BA)，会规避原字符串中已有字符。

实例方法 `to_list` **还原上述过程**并返回列表。字符与对象映射存储在上下文中，因此**仅在同一上下文中才可还原！**且可能存在实例化时原字符串包含已被分配的字符的情况，届时会抛出 `models.exc.CodePointConflictError`，可在此之前通过类方法 `clear_map` 清空映射。

该类继承自 `str`，且覆写了绝大多数方法使其返回为 `InlineStr` 实例。若经过操作后变成了普通 `str` 实例，可以通过 `InlineStr(str)` 获取实例。

### `is_version_newer`

判断第一个版本号是否比第二个更新。

### `charclass_escape`

只转义正则字符集中有特殊含义的字符，需要传入方括号（不包括）之间的整个字符串。

### `asub` / `series_asub`

`re.sub` 的 `repl` 参数接受异步协程的版本。

## `utils.unit`

### `num2chs` / `num2chs10`

将阿拉伯数字转换为简体中文数字描述。

### `parse_size`

从 (humanfriendly)[https://github.com/xolox/python-humanfriendly] 复制过来的将基于 [IEC 60027-2](https://zh.wikipedia.org/wiki/IEC_60027) 的字节数量描述转化为字节数。

### `chs2sec`

将中文时间段描述转化为秒数。建议使用 [cn2t](https://github.com/WFLing-seaer/cn2t)。

## `utils.apscheduler`

### `TimeTrigger`

实现延时触发。[示例](计划任务.md#使用与示例)

## `utils.sqlalchemy`

仅支持 SQLite 和 postgreSQL。

### `upsert`

返回 Insert 对象。可通过 `returning` 返回更新后的值。关键字参数中不能引用列值。

[使用示例](./长效数据.md#示例)

### `insert_ignore`

返回 Insert 对象。若插入，`returning` 返回插入的值；若忽略，`returning` 返回原有值。关键字参数中不能引用列值。

使用方法同上。

## 中止 Aha 进程

```python
import core.status

core.status.main_task.cancel()
```