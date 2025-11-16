# Message API

这里仅列举绝大多数 API，其余 API 可以在 [已有适配器](../../已有适配器/README.md) 中找到。

部分 API 在[事件对象](../../数据结构/事件对象.md)中存在便捷方法。

## send_msg

发送消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| msg | str \| Sequence[[MsgSeg](../../数据结构/消息序列与消息段.md#msgseg) \| str] \| [MsgSeg](../../数据结构/消息序列与消息段.md#msgseg) \| None | 消息内容。不支持 [InlineStr](../内置轮子与最佳实践/零碎%20utils.md#inlinestr)。 |
| at | str \| int \| None | 若有值视为平台用户 ID，自动在消息内容前部添加 [At](../../数据结构/消息序列与消息段.md#at) 。 |
| reply | str \| int \| None | 若有值视为消息 ID，自动在消息内容前部添加 [Reply](../../数据结构/消息序列与消息段.md#reply) 。 |
| image | str \| Path \| None | 若有值视为图片文件路径或 URL，自动在消息内容尾部添加 [Image](../../数据结构/消息序列与消息段.md#image) 。 |

**返回**: 消息 ID (str)

## send_raw_msg

发送协议框架的数据格式的消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| data | Any | 目标协议消息内容数据格式。 |

**返回**: 消息 ID (str)

## send_image

发送图片消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| image | str \| Path | 接受路径或 URL。 |

**返回**: 消息 ID (str)

## send_record

发送语音消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| file | str \| Path | 接受路径或 URL。 |

**返回**: 消息 ID (str)

<!--## send_dice

发送骰子消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| value | int | 骰子点数。默认为 1。 |

**返回**: 消息 ID (str)

## send_rps

发送猜拳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| value | int | 猜拳点数。默认为 1。 |

**返回**: 消息 ID (str)-->

## send_file

发送文件消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| file | str \| Path | 接受路径或 URL。 |
| name | str \| None | 文件名，为空时自动从路径提取。默认为 `None`。 |

**返回**: 消息 ID (str)

## send_music

发送音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| url | str | 卡片跳转链接。 |
| audio | str \| None | 媒体链接。 |
| title | str \| None | 音乐标题。 |
| content | str \| None | 更多信息，一般是歌手。 |
| image | str \| Path \| None | 卡片封面，接受路径或 URL。 |

**返回**: 消息 ID (str)

## send_forward_msg_by_id

通过消息 ID 列表发送合并转发消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| messages | Sequence[str \| int] | 消息 ID 序列。 |

**返回**: 消息 ID (str)

## poke

发送戳一戳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |

## get_msg

获取消息信息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| message_id | str \| int | 消息 ID。 |

**返回**: [RetrievedMessage](../../数据结构/消息序列与消息段.md#message)

## get_forward_msg

获取合并转发消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| message_id | str \| int | 合并转发消息 ID。 |

**返回**: [Forward](../../数据结构/消息序列与消息段.md#forward)

## get_file_src

通过消息段获取文件的 URL，若无法获取 URL 则获取内容。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| msg_seg | [Downloadable](../../数据结构/消息序列与消息段.md#downloadable) | 可下载的消息段（如 `Image`、`Record`、`File` 等）。 |
| record_format | [AudioFormat](../../数据结构/API%20相关.md#modelsapiaudioformat) | 当 `msg_seg` 为 `Record` 类型时，指定音频格式。默认为 `AudioFormat.MP3`。 |

**返回**: 文件 URL 或二进制内容 (str | bytes)。

## get_file

获取文件信息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| file_id | str | 文件 ID。 |

**返回**: [File](../../数据结构/消息序列与消息段.md#file)

## get_reaction_users

获取指定表情回复参与的用户。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| message_id | str \| int | 消息 ID。 |
| emoji_id | str \| int | 表情 ID。 |

**返回**: 用户列表 (Sequence[[ReactionUser](../../数据结构/API%20相关.md#modelsapireactionuser)])

## set_reaction

设置表情回应。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| message_id | str \| int | 消息 ID。 |
| emoji_id | str \| int | 表情 ID。 |
| set | bool | 是否设置。默认为 `True`。 |

## delete_msg

撤回消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| message_id | str \| int | 消息 ID。 |

## set_input_status

设置输入状态。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| status | int | 状态码，0 表示“对方正在说话”，1 表示“对方正在输入”。 |
