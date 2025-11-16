# API 数据结构

适配器的返回值不一定能具备所有属性，此时属性值会为 `None`。

## models.api.ReactionUser

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| user_id | str | 平台用户 ID |
| nickname | str | 用户昵称 |
| avatar_url | str | 用户头像源 |

## models.api.Sex

枚举类型。

| 成员 | 值 | 概述 |
| :---: | :---: | :---: |
| MALE | "male" | 男性 |
| FEMALE | "female" | 女性 |
| UNKNOWN | "unknown" | 未知 |

## models.api.Role

枚举类型。

| 成员 | 值 | 概述 |
| :---: | :---: | :---: |
| OWNER | "owner" | 群主 |
| ADMIN | "admin" | 管理员 |
| MEMBER | "member" | 普通成员 |

## models.api.EssenceMessage

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| sender_id | str | 消息发送者平台用户 ID |
| sender_nick | str | 消息发送者昵称 |
| operator_id | str | 操作者平台用户 ID |
| operator_nick | str | 操作者昵称 |
| message_id | str | 消息 ID |
| operator_time | datetime | 设为精华消息的时间 |
| message | [MessageChain](../数据结构/消息序列与消息段.md#消息序列) | 消息内容 |
| message_str | str | 字符串格式的消息内容 |

### EssenceMessage.get_msg_inline()

获取 [InlineStr](../模块开发/内置轮子与最佳实践/零碎%20utils.md#inlinestr) 格式的消息内容。

## models.api.GroupFile

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| group_id | str | 群号 |
| file_id | str | 文件 ID |
| file_name | str | 文件名 |
| busid | int | 文件传输类型 ID |
| file_size | int | 文件大小 （字节） |
| upload_time | datetime | 上传时间 |
| dead_time | datetime | 文件过期时间 |
| modify_time | datetime | 最后修改时间 |
| download_times | int | 下载次数 |
| uploader | str | 上传者平台用户 ID |
| uploader_name | str | 上传者昵称 |

## models.api.GroupFolder

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| group_id | str | 群号 |
| folder_id | str | 文件夹 ID |
| folder | str | 文件夹路径或标识 |
| folder_name | str | 文件夹名称 |
| create_time | datetime | 创建时间 |
| creator | str | 创建者平台用户 ID |
| creator_name | str | 创建者昵称 |
| total_file_count | int | 文件夹内文件总数 |

## models.api.GroupFiles

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| files | list[[GroupFile](#modelsapigroupfile)] | 文件列表 |
| folders | list[[GroupFolder](#modelsapigroupfolder)] | 文件夹列表 |

## models.api.GroupInfo

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| group_all_shut | bool | 全员禁言状态 |
| group_remark | str | 群备注 |
| group_id | str | 群号 |
| group_name | str | 群名称 |
| member_count | int \| None | 当前群成员数量 |

## models.api.GroupMemberInfo

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| group_id | str | 群号 |
| user_id | str | 用户平台 ID |
| nickname | str \| None | 用户昵称 |
| card | str \| None | 群昵称 |
| sex | [Sex](#modelsapisex) | 性别 |
| age | int \| None | 年龄 |
| area | str | 地区 |
| join_time | datetime \| None | 加入群的时间 |
| last_sent_time | datetime \| None | 最后发言时间 |
| unfriendly | bool | 是否被标记为不友好用户 |
| is_robot | bool | 是否为机器人账号 |
| shut_up_time | datetime \| None | 禁言截止时间 |
| role | [Role](#modelsapirole) | 群权限 |
| title | str \| None | 群头衔 |

## models.api.GroupMembers

继承自 frozenset。

### GroupMembers.is_admin()

判断指定用户平台 ID 是否为管理员或群主。

| 参数 | 类型 | 概述 |
| --- | --- | --- |
| user_id | str | 用户平台 ID |

**返回**：bool

### GroupMembers.is_manager_of()

判断第一个用户是否对第二个用户具有管理权限。

| 参数 | 类型 | 概述 |
| --- | --- | --- |
| manager | str | 管理者用户平台 ID |
| subordinate | str | 下属用户平台 ID |

**返回**：bool

### GroupMembers.filter_by_last_sent_time_upto_now()

返回最后发言时间在指定秒数以内的成员列表。仅对 `last_sent_time` 字段不为 `None` 的成员进行判断。

| 参数 | 类型 | 概述 |
| --- | --- | --- |
| seconds | int | 距离当前时间的秒数 |

**返回**：[GroupMembers](#modelsapigroupmembers)

### GroupMembers.filter_by_role()

返回具有指定群权限等级的成员列表。

| 参数 | 类型 | 概述 |
| --- | --- | --- |
| role | [Role](#modelsapirole) |  |

**返回**：[GroupMembers](#modelsapigroupmembers)

### GroupMembers.filter_by_role_not_in()

返回群角色不在指定列表中的成员列表。

| 参数 | 类型 | 概述 |
| --- | --- | --- |
| roles | Container[[Role](#modelsapirole)] |  |

**返回**：[GroupMembers](#modelsapigroupmembers)

### GroupMembers.filter_by_have_title()

返回拥有群头衔（`title` 字段不为空字符串或 `None`）的成员列表。

**参数**：无

**返回**：[GroupMembers](#modelsapigroupmembers)

## models.api.LoginInfo

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| nickname | str | 昵称 |
| user_id | str | 账户平台 ID |

## models.api.Friend

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| user_id | str | 好友用户平台 ID |
| nickname | str | 好友昵称 |
| remark | str \| None | 好友备注 |
| sex | str \| None | 性别 |
| level | int \| None | 好友等级 |
| age | int \| None | 年龄 |
| birthday | date \| None | 生日 |
| phone_num | str \| None | 手机号码 |
| email | str \| None | 电子邮箱 |
| category_id | int \| None | 所属好友分组 ID |

## models.api.FriendCategory

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| category_id | int | 好友分组 ID |
| category_name | str | 好友分组名称 |
| online_count | int \| None | 分组在线好友数量 |
| friends | list[[Friend](#modelsapifriend)] | 分组好友列表 |

## models.api.LastestMsgs

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| peer_id | str | 对端平台 ID |
| remark | str | 备注 |
| msg_time | datetime | 最新一条消息的发送时间 |
| chat_type | [MessageSubType](./事件对象.md#messagesubtype) | 聊天类型 |
| message_id | str | 最新一条消息的消息 ID |
| sender | [MessageSender](./事件对象.md#messagesender) | 发送者的昵称 |
| peer_name | str | 对端的名称（如好友昵称或群名称） |
| latest_msg | [Message](./事件对象.md#message) | 最新一条消息 |

## models.api.Stranger

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 概述 |
| --- | --- | --- |
| user_id | str | 用户平台 ID |
| nickname | str | 昵称 |
| sex | str | 性别 |
| age | int \| None | 年龄 |
| level | int \| None | 等级 |
| bio | str \| None | 个性签名 |
| reg_time | datetime \| None | 注册时间 |
| is_vip | bool \| None | 是否为 VIP 用户 |
| remark | str \| None | 备注 |

## models.api.AudioFormat

枚举类型。

| 成员 | 值 |
| :---: | :---: |
| MP3 | "mp3" |
| AMR | "amr" |
| WMA | "wma" |
| M4A | "m4a" |
| OGG | "ogg" |
| WAV | "wav" |
| FLAC | "flac" |
| SPX | "spx" |
