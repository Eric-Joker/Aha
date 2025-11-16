# Account API

这里仅列举绝大多数 API，其余 API 可以在 [已有适配器](../../已有适配器/README.md) 中找到。

部分 API 在[事件对象](../../数据结构/事件对象.md)中存在便捷方法。

## set_profile

设置个人资料。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| nickname | str | 昵称。 |
| personal_note | str | 个性签名。 |
| sex | [Sex](../../数据结构/API%20相关.md#modelsapisex) | 性别。 |

## set_online_status

设置在线状态。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| status | int \| str | 状态。 |
| ext_status | Any | 状态扩展信息。 |

## set_avatar

设置头像。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| file | str \| [File](../../数据结构/消息序列与消息段.md#file) \| [Image](../../数据结构/消息序列与消息段.md#image) |  |

## set_bio

设置个人签名。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| content | str | 签名内容。 |

## get_login_info

获取登录账号信息。

**返回**: [LoginInfo](../../数据结构/API%20相关.md#modelsapilogininfo)

## get_friends_with_category

获取带分组的好友列表。

**返回**: list[[FriendCategory](../../数据结构/API%20相关.md#modelsapifriendcategory)]

## process_friend_add_request

处理加好友请求。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| flag | str | 请求标识。 |
| approve | bool | 是否同意。 |
| remark | str \| None | 通过后好友备注。 |

## get_friends

获取好友列表。

**返回**: frozenset[[Friend](../../数据结构/API%20相关.md#modelsapifriend)]

## get_user_by_friend

通过好友列表获取用户信息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |

**返回**: [Friend](../../数据结构/API%20相关.md#modelsapifriend) | None

## delete_friend

删除好友。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |
| block | bool | 是否同时拉黑。默认为 `False`。 |
| both | bool | 是否双向删除。默认为 `True`。 |

## set_friend_remark

设置好友备注。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |
| remark | str | 备注名称。 |

## get_last_msg_per_conv

获取每个会话的最后一条消息。

**返回**: list[[LastestMsgs](../../数据结构/API%20相关.md#modelsapilastestmsgs)]

## mark_group_msg_as_read

标记群聊消息为已读。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |

## mark_private_msg_as_read

标记私聊消息为已读。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |

## mark_all_as_read

标记所有消息为已读。

## get_stranger_info

获取陌生人信息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |

**返回**: [Stranger](../../数据结构/API%20相关.md#stranger)

## get_card_by_search

获取群成员名片，不存在该成员时从陌生人、好友渠道获取昵称。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |
| group_id | str \| int \| None | 若提供，优先从该群获取群名片。 |
| force_return_card | bool | 若为 `True`，返回元组 `(card, nickname)`；否则返回 `card or nickname`。默认为 `False`。 |

**返回**: ↑ | None

## get_nickname

获取陌生人昵称，不存在时返回 uid。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |

**返回**: str

## fetch_collected_stickers

获取收藏的表情包。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| count | int | 获取数量，默认为 48。 |

**返回**: list[[Sticker](../../数据结构/消息序列与消息段.md#sticker)]

## get_user_status

获取指定用户账号状态。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |

**返回**: [UserStatus](../../数据结构/API%20相关.md#userstatus)