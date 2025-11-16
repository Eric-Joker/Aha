# Private API

这里仅列举绝大多数 API，其余 API 可以在 [已有适配器](../../已有适配器/README.md) 中找到。

部分 API 在[事件对象](../../数据结构/事件对象.md)中存在便捷方法。

## send_private_msg

发送私聊消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| msg | str \| Sequence[[MsgSeg](../../数据结构/消息序列与消息段.md#msgseg) \| str] \| [MsgSeg](../../数据结构/消息序列与消息段.md#msgseg) \| None | 消息内容。不支持 [InlineStr](../内置轮子与最佳实践/零碎%20utils.md#inlinestr)。 |
| at | str \| int \| None | 若有值视为平台用户 ID，自动在消息内容前部添加 [At](../../数据结构/消息序列与消息段.md#at) 。 |
| reply | str \| int \| None | 若有值视为消息 ID，自动在消息内容前部添加 [Reply](../../数据结构/消息序列与消息段.md#reply) 。 |
| image | str \| Path \| None | 若有值视为图片文件路径或 URL，自动在消息内容尾部添加 [Image](../../数据结构/消息序列与消息段.md#image) 。 |

**返回**: 消息 ID (str)

## send_private_raw_msg

发送协议框架的数据格式的私聊消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| data | Any | 目标协议消息内容数据格式。 |

**返回**: 消息 ID (str)

## send_private_image

发送私聊图片消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| image | str \| Path | 接受路径或 URL。 |

**返回**: 消息 ID (str)

## send_private_record

发送私聊语音消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| file | str \| Path | 接受路径或 URL。 |

**返回**: 消息 ID (str)

<!--## send_private_dice

发送私聊骰子消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| value | int | 骰子点数。默认为 1。 |

**返回**: 消息 ID (str)

## send_private_rps

发送私聊猜拳消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| value | int | 猜拳点数。默认为 1。 |

**返回**: 消息 ID (str)-->

## send_private_file

发送私聊文件消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| file | str \| Path | 接受路径或 URL。 |
| name | str \| None | 文件名，为空时自动从路径提取。默认为 `None`。 |

**返回**: 消息 ID (str)

## send_private_music

发送私聊音乐分享消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| url | str | 卡片跳转链接。 |
| audio | str \| None | 媒体链接。 |
| title | str \| None | 音乐标题。 |
| content | str \| None | 更多信息，一般是歌手。 |
| image | str \| Path \| None | 卡片封面，接受路径或 URL。 |

**返回**: 消息 ID (str)

## send_private_forward_msg_by_id

通过消息 ID 列表发送私聊合并转发消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| messages | Sequence[str \| int] | 消息 ID 序列。 |

**返回**: 消息 ID (str)

## friend_poke

私聊戳一戳。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |

## get_private_msg_history

获取私聊消息历史。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| message_seq | str \| int | 起始消息序列号或消息 ID。 |
| number | int | 获取数量，默认为 20。 |
| reverseOrder | bool | 是否倒序，默认为 `False`。 |

**返回**: list[[RetrievedMessage](../../数据结构/消息序列与消息段.md#message)]

## upload_private_file

上传私聊文件。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| file | str | 本地文件路径。 |
| name | str | 文件名。 |
