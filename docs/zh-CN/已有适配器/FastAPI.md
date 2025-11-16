
# FastAPI

| 平台    | 通讯方式   |
| --- | --- |
| Web 服务端 | Web 服务 |

至多建立一个 FastAPI 服务。通过 `fastapi_modules` 目录下的路由与 Web 服务交互。

具有请求体签名验证中间件，采用 `ed25519`，请求时要将签名放入 `signature` 请求头。

| 配置项 | 类型   | 说明 | 示例 |
| --- | --- | --- | --- |
| host   | str |        | `0.0.0.0` |
| port   | int |
| public_key | str | `ed25519` 公钥文件。 |
| lang | str | `fastapi_modules` 中的回调上报事件时若未指定语言的默认语言。详见 [本地化](./模块开发/本地化.md) |  |

## `fastapi_modules` 目录下的模块示例

```python
from typing import Annotated
from fastapi import Body
from bots.fastapi import FastAPI, app

@app.post("/test")
async def handle_rhp_sub(body: Annotated[str, Body(..., media_type="text/plain")]):
    await FastAPI.post("web_test", body, lang="en") # 向普通的 Aha 模块发送键为 `web_test` 的 EXTERNAL 事件。
    return {"status": "request_queued"}
```
