# Aha ID

> 由于 Aha 是一个跨平台的后端框架，为了一致化数据，我们实现了 Aha ID 机制，用于标识用户、群组。

Aha ID 的数据类型为 int，范围为 ±2^63-1。

在初始状态下，全平台用户的 Aha ID 均是基于哈希唯一的，群组的也是。

Aha ID 允许共用映射，即不同或相同平台的用户可以共用同一个 Aha ID，使业务逻辑认为为一个用户。

我们推荐在业务逻辑中**尽可能使用 Aha ID 作为用户/群组唯一标识**，而不是使用平台的 ID。

> Aha ID 不得直接用于调用 API，必须先进行[额外转换](#从-aha-id-获取平台个体)！

## 从平台个体获取 Aha ID

[事件对象](../数据结构/事件对象.md)提供了便捷获取方法。

```python
from core.dispatcher import on_message
from core.identity import user2aha_id, group2aha_id
from models.api import Message

@on_message()
async def _(event: Message):
    # 当前处于事件上下文中，默认行为与 event.group2aha_id() 一致
    aha_id: int = await group2aha_id()
    aha_id: int = await user2aha_id("123456")  # 获取当前事件上下文相同平台的指定用户的 Aha ID。

# 当前不一定处于事件上下文中
aha_id: int = await user2aha_id("QQ", "123456")  # 获取指定平台指定用户的 Aha ID。
```

## 从 Aha ID 获取平台个体

```python
from core.identity import aha_id2user, aha_id2group
from models.core import User, Group

u: tuple[User, ...] = aha_id2user(123456)
g: tuple[Group, ...] = aha_id2group(123456)
```

## 将平台个体映射到指定的 Aha ID

该行为由内置模块 `id_mapper` 实现，这里懒得写。
