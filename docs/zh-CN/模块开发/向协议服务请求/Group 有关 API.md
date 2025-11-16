# Group API

这里仅列举绝大多数 API，其余 API 可以在 [已有适配器](../../已有适配器/README.md) 中找到。

部分 API 在[事件对象](../../数据结构/事件对象.md)中存在便捷方法。

## send_group_msg

发送群聊消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| msg | str \| Sequence[[MsgSeg](../../数据结构/消息序列与消息段.md#msgseg) \| str] \| [MsgSeg](../../数据结构/消息序列与消息段.md#msgseg) \| None | 消息内容。不支持 [InlineStr](../内置轮子与最佳实践/零碎%20utils.md#inlinestr)。 |
| at | str \| int \| None | 若有值视为平台用户 ID，自动在消息内容前部添加 [At](../../数据结构/消息序列与消息段.md#at) 。 |
| reply | str \| int \| None | 若有值视为消息 ID，自动在消息内容前部添加 [Reply](../../数据结构/消息序列与消息段.md#reply) 。 |
| image | str \| Path \| None | 若有值视为图片文件路径或 URL，自动在消息内容尾部添加 [Image](../../数据结构/消息序列与消息段.md#image) 。 |

**返回**: 消息 ID (str)

## send_group_raw_msg

发送协议框架的数据格式的群聊消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| data | Any | 目标协议消息内容数据格式。 |

**返回**: 消息 ID (str)

## send_group_image

发送群聊图片消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| image | str \| Path | 接受路径或 URL。 |

**返回**: 消息 ID (str)

## send_group_record

发送群聊语音消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file | str \| Path | 接受路径或 URL。 |

**返回**: 消息 ID (str)

<!--## send_group_dice

发送群聊骰子消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| value | int | 骰子点数。默认为 1。 |

**返回**: 消息 ID (str)

## send_group_rps

发送群聊猜拳消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| value | int | 猜拳点数。默认为 1。 |

**返回**: 消息 ID (str)-->

## send_group_file

发送群聊文件消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file | str \| Path | 接受路径或 URL。 |
| name | str \| None | 文件名，未传递时自动从路径提取。 |

**返回**: 消息 ID (str)

## send_group_music

发送群聊音乐分享消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| url | str | 卡片跳转链接。 |
| audio | str \| None | 媒体链接。 |
| title | str \| None | 音乐标题。 |
| content | str \| None | 更多信息，一般是歌手。 |
| image | str \| Path \| None | 卡片封面，接受路径或 URL。 |

**返回**: 消息 ID (str)

## send_group_forward_msg_by_id

通过消息 ID 列表发送群聊合并转发消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| messages | Sequence[str \| int] | 消息 ID 序列。 |

**返回**: 消息 ID (str)

## group_poke

群聊戳一戳。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |

## group_kick_members

批量踢群成员。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_ids | Sequence[str \| int] | 用户 ID 列表。 |
| reject_add_request | bool | 是否拒绝再次加群请求。默认为 `False`。 |

## group_kick

群踢人。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |
| reject_add_request | bool | 是否拒绝再次加群请求。默认为 `False`。 |

## group_ban

群禁言。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |
| duration | int | 禁言秒数。默认为 0（解除禁言）。 |

**返回**: 操作是否成功 (bool)

## set_group_whole_ban

设置群全员禁言。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| enable | bool | 是否开启全员禁言。 |

## set_group_admin

设置群管理员。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |
| enable | bool | 是否设置为管理员。 |

## group_leave

退出群聊。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| is_dismiss | bool | 是否解散群（仅群主可用）。默认为 `False`。 |

## set_group_special_title

为用户设置群专属头衔。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |
| special_title | str | 专属头衔，空字符串表示取消。 |

## process_group_join_request

处理加群请求。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| flag | str | 请求标识。 |
| approve | bool | 是否同意。 |
| reason | str \| None | 拒绝理由。 |

## set_group_card

改群友的群昵称。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |
| card | str | 新群昵称，空字符串表示清除。 |

## get_card

获取群成员名片，不存在时自动选择昵称。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |

**返回**: 群名片或昵称 (str)，若成员不存在返回 `None`。

## is_admin

判断用户是否为群管理员。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |

**返回**: bool

## get_group_msg_history

获取群消息历史。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| message_seq | str \| int | 起始消息序列号或消息 ID。 |
| number | int | 获取数量，默认为 20。 |
| reverseOrder | bool | 是否倒序，默认为 `False`。 |

**返回**: list[[RetrievedMessage](../../数据结构/消息序列与消息段.md#message)]

## set_essence_msg

设置精华消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| message_id | str \| int | 消息 ID。 |

## delete_essence_msg

删除精华消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| message_id | str \| int | 消息 ID。 |

## get_essence_msg_list

获取群精华消息列表。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |

**返回**: list[[EssenceMessage](../../数据结构/API%20相关.md#modelsapiessencemessage)]

## move_group_file

移动群文件。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file_id | str | 文件 ID。 |
| current_parent_directory | str | 当前父目录 ID。 |
| target_parent_directory | str | 目标父目录 ID。 |

## trans_group_file

转存为永久文件。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file_id | str | 文件 ID。 |

## rename_group_file

重命名群文件。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file_id | str | 文件 ID。 |
| new_name | str | 新文件名。 |

## upload_group_file

上传群文件。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file | str | 本地文件路径。 |
| name | str | 文件名。 |
| folder | str | 目标文件夹 ID。 |

## create_group_file_folder

创建群文件文件夹。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| folder_name | str | 文件夹名称。 |

## group_file_folder_makedir

按路径创建群文件夹。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| path | str | 文件夹路径（如 `/foo/bar/`）。 |

**返回**: str（创建的文件夹 ID）

## delete_group_file

删除群文件。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file_id | str | 文件 ID。 |

## delete_group_folder

删除群文件夹。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| folder_id | str | 文件夹 ID。 |

## get_group_root_files

获取群根目录文件列表。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file_count | int | 返回的文件数量上限，默认为 50。 |

**返回**: [GroupFiles](../../数据结构/API%20相关.md#modelsapigroupfiles)

## get_group_files_by_folder

获取文件夹内文件列表。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| folder_id | str | 文件夹 ID。 |
| file_count | int | 返回的文件数量上限，默认为 50。 |

**返回**: [GroupFiles](../../数据结构/API%20相关.md#modelsapigroupfiles)

## get_group_file_url

获取群文件 URL。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file_id | str | 文件 ID。 |

**返回**: str（文件下载 URL）

## get_group_info

获取群信息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |

**返回**: [GroupInfo](../../数据结构/API%20相关.md#modelsapigroupinfo)

## get_group_info_raw

获取协议框架原始群信息数据。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |

**返回**: 协议框架原始数据

## get_group_member_info

获取群成员信息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| user_id | str \| int | 目标用户 ID。 |

**返回**: [GroupMemberInfo](../../数据结构/API%20相关.md#modelsapigroupmemberinfo)

## get_group_members

获取群成员列表。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |

**返回**: [GroupMembers](../../数据结构/API%20相关.md#modelsapigroupmembers)

## get_group_list

获取群列表。

**返回**: list[GroupInfo]

## get_user_by_groups

从所有群中查询群成员信息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |

**返回**: [GroupMemberInfo](../../数据结构/群组.md#groupmemberinfo) | None

## get_group_shut_list

获取群禁言列表。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |

**返回**: [GroupMembers](../../数据结构/群组.md#groupmembers)

## set_group_remark

设置群备注。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| remark | str | 备注名称。 |

## set_group_sign

群签到。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |

## set_group_avatar

设置群头像。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| file | str | 图片 URL。 |

## set_group_name

设置群名。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| name | str | 新群名。 |
