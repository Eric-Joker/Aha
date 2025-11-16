# Support API

这里仅列举绝大多数 API，其余 API 可以在 [已有适配器](../../已有适配器/README.md) 中找到。

## get_version_info

获取 API 版本信息。

**返回**: [APIVersion](../../数据结构/API%20相关.md#apiversion)

## start_server

启动协议框架服务，执行配置文件中 `bots.[].start_server_command` 值。

**返回**: 进程返回码 (int | None)，未配置命令时引发 `NotImplementedError`。

## stop_server

停止后端服务。

## restart_server

重启后端服务。

**返回**: tuple[int | None, int | None]，未配置 `bots.[].start_server_command` 时引发 `NotImplementedError`。

## get_status

获取协议服务状态。

**返回**: [HeartbeatStatus](../../数据结构/事件对象.md#heartbeatstatus)
