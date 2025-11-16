# NapCat

| 平台    | 通讯方式   |
| --- | --- |
| QQ      | Websocket |

| 配置项 | 类型   | 说明 | 示例 |
| --- | --- | --- | --- |
| uri    | str |        | `ws://127.0.0.1:3000` |
| token  | str |
| start_server_command | str | 当前系统环境的命令语句。调用 `restart_server` 等 API 时会调用。 |
| retry_config | dict[dict \| list] | 基于 [`tenacity`](https://github.com/jd/tenacity) 的重试配置，键支持 [`stop 方法`](https://tenacity.readthedocs.io/en/latest/api.html#stop-functions) 和 [`wait 方法`](https://tenacity.readthedocs.io/en/latest/api.html#wait-functions)，通过 kwargs 声明参数。| <pre><code>wait_exponential:<br>  multiplier: 1<br>  max: 30<br>  exp_base: 2<br>  min: 1</code></pre> |
| lang | str | 语言代码。 | `zh-CN` |

## 独有 API

### get_group_info

与 [get_group_info](./模块开发/向协议服务请求/Group%20有关%20API.md#get_group_info) 相同，但返回的 `GroupInfo` 对象额外包含 `max_member_count` 属性。

### get_group_member_info

与 [get_group_member_info](./模块开发/向协议服务请求/Group%20有关%20API.md#get_group_member_info) 相同，但返回的 [GroupMemberInfo](../../数据结构/群组.md#groupmemberinfo) 对象额外包含如下属性：

| 属性 | 类型 | 描述 |
| --- | --- | --- |
| activity_level | str | 活跃度等级。 |
| title_expire_time | datetime | 群头衔过期时间。 |
| card_changeable | bool | 是否允许修改其群名片。 |

### get_group_members

与 [get_group_members](./模块开发/向协议服务请求/Group%20有关%20API.md#get_group_members) 相同，但返回的 [GroupMembers](../../数据结构/群组.md#groupmembers) 额外包含如下方法：

#### GroupMembers.filter_by_level_ge

返回等级大于等于指定值的成员列表。

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| level | int | 等级阈值（包含）。 |

**返回**：[GroupMembers](../../数据结构/群组.md#groupmembers)

#### GroupMembers.filter_by_level_le

返回等级小于等于指定值的成员列表。

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| level | int | 等级阈值（包含）。 |

**返回**：[GroupMembers](../../数据结构/群组.md#groupmembers)

### get_group_honor_info

获取群荣誉信息。

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| group_id | str |  |
| type | [HonorType](#botsnapcathonortype) \| None |  |

**返回**：[GroupHonor](#botsnapcatgrouphonor)

### set_online_status

与 [set_online_status](./模块开发/向协议服务请求/Account%20有关%20API.md#set_online_status) 相同。参数参考 [NapCatQQ Docs](https://napcat.apifox.cn/411631077e0)，其中 `status` 为 `10` 时 `ext_status` 代表 `battery_status`。

### send_like

点赞。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标用户 ID。 |
| times | int | 点赞次数，默认为 1。 |

**返回**: dict[str, Any]（平台原始响应）

### send_platform_music

发送平台音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

拥有第二个签名: 允许同时省略 `user_id`、 `group_id` 和 `bot` 参数，届时自动从事件上下文中获取。

在具有完整参数的签名中，所有参数均为 kwargs only。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int \| None | 目标的平台用户 ID。 |
| group_id | str \| int \| None | 目标的平台群组 ID。为 `None` 时发送私聊消息。 |
| platform | Literal["qq", "163"] | 音乐平台枚举。 |
| id | str \| int | 音乐 ID。 |

**返回**: 消息 ID (str)

### send_group_platform_music

发送群聊平台音乐分享消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| group_id | str \| int | 群组 ID。 |
| platform | Literal["qq", "163"] | 音乐平台枚举。 |
| id | str \| int | 音乐 ID。 |

**返回**: 消息 ID (str)

### send_platform_private_music

发送私聊平台音乐分享消息。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| user_id | str \| int | 目标的平台用户 ID。 |
| platform | Literal["qq", "163"] | 音乐平台枚举。 |
| id | str \| int | 音乐 ID。 |

**返回**: 消息 ID (str)

### create_collection

收藏。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| raw_data | str | 内容。 |
| brief | str | 标题。 |

### get_level_by_search

从陌生人、好友渠道获取用户等级

**返回**: int | None

### get_ai_characters

获取 AI 声聊角色列表

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| group_id | str |  |
| chat_type | Literal[1, 2] |  |

**返回**: list[[AICharacter](#botsnapcataicharacter)]

### get_ai_record

获取 AI 声聊语音

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| group_id | str |  |
| character_id | str |  |
| text | str |  |

**返回**: 链接 (str)

### can_send_image

检查是否可以发送图片

**返回**: bool

### can_send_record

检查是否可以发送语音

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| group_id | str |  |

**返回**: bool

### ocr_image

图片 OCR，仅 Windows。

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| image | str \| [Image](./数据结构/消息序列与消息段.md#image) \| [File](./数据结构/消息序列与消息段.md#file) |  |

**返回**: list[dict[str, Any]]

## 独有数据结构

### bots.napcat.GroupHonor

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 描述 |
| --- | --- | --- |
| group_id | str |  |
| current_talkative | [GroupHonorUser](#botsnapcatgrouphonoruser) |  |
| talkative_list | list[[GroupHonorUser](#botsnapcatgrouphonoruser)] |  |
| performer_list | list[[GroupHonorUser](#botsnapcatgrouphonoruser)] |  |
| legend_list | list[[GroupHonorUser](#botsnapcatgrouphonoruser)] |  |
| emotion_list | list[[GroupHonorUser](#botsnapcatgrouphonoruser)] |  |

### bots.napcat.GroupHonorUser

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 描述 |
| --- | --- | --- |
| user_id | str |  |
| nickname | str |  |
| avatar | str |  |
| description | str \| None |  |

### bots.napcat.HonorType

枚举类型。

| 成员 | 值 |
| :---: | :---: |
| TALKATIVE | "talkative" |
| PERFORMER | "performer" |
| EMOTION | "emotion" |

### bots.napcat.AICharacter

[Pydantic](https://github.com/pydantic/pydantic) Model。

| 属性 | 类型 | 描述 |
| --- | --- | --- |
| character_id | str |  |
| character_name | str |  |
| preview_url | str |  |
