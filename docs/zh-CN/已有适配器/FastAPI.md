
# FastAPI

| 平台    | 通讯方式   |
| --- | --- |
| Web 服务端 | Web 服务 |

至多建立一个 Uvicorn 服务。通过 `fastapi_modules` 目录下的路由与 Web 服务交互。

| 配置项 | 类型   | 说明 | 示例 |
| --- | --- | --- | --- |
| **kwargs | | [uvicorn.run 的参数](https://uvicorn.dev/settings) | <pre><code>host: 0.0.0.0<br>port: 6550</code></pre> |
| public_key | str | `ed25519` 公钥文件，用于[内置请求验证](#请求验证)。默认为项目根目录的 `ed25519.pem`。可不提供。|
| lang | str | 用于 [本地化](../模块开发/本地化.md)，`fastapi_modules` 中的回调上报事件时若未指定语言的默认语言。可不提供。|  |

## `fastapi_modules` 目录下的模块示例

```python
from typing import Annotated
from fastapi import Body
from bots.fastapi import FastAPI, app

@app.post("/test")
async def _(body: Annotated[str, Body(..., media_type="text/plain")]):
    await FastAPI.post("web_test", body, lang="en") # 向普通的 Aha 模块发送键为 `web_test` 的 EXTERNAL 事件。
    result = await FastAPI.get("web_test", body, "en", timeout=10) # 同上，且等待返回值。timeout 默认为 64800 秒。
    return {"status": "request_queued"}
```

> 请尽可能维护键的唯一性，避免不同模块之间的<small style="color: gray;">~~默契~~</small>冲突。

## 独有 API

### set_result

为指定事件设置返回值。

| 属性 | 类型 | 描述 |
| --- | --- | --- |
| key | str | [External](.../模块开发/订阅与发布事件.md) 事件标识，由 `FastAPI.get` 的 `key` 参数指定。 |
| data | Picklable | 要返回的数据。 |

### send_msg

重定向至 [set_result](#set_result)，其中 `user_id` 参数被重定向至 `key`，`msg` 参数被重定向至 `data`。

## 请求验证

内置建立连接时防重放和 **ed25519** 签名验证的中间件。该中间件不会验证请求体，建议使用 HTTPS 或 WSS。

端点通过 `bots.fastapi.verify` 装饰器使对应的 `path` 执行该验证逻辑。

未找到公钥文件时不进行验证；若存在 `signature` 请求头但未提供公钥文件则返回 503。

要求如下请求头：

| 请求头 | 描述 |
| --- | --- |
| Timestamp | 秒级时间戳的大端字节序 base64 |
| Nonce | 16 字节随机 base64 挑战值 |
| Signature | 对由 `|` 分割的上述两请求头值的字符串进行签名的 base64 |

### curl 示例

```shell
timestamp_b64=$(printf "%016x" $(date +%s) | xxd -r -p | openssl enc -base64 -A)
nonce_b64=$(openssl rand -base64 16 | tr -d '\n')

tmpfile=$(mktemp)
printf "%s" "${timestamp_b64}|${nonce_b64}" > "$tmpfile"
signature=$(openssl pkeyutl -sign -inkey private.pem -rawin -in "$tmpfile" | openssl enc -base64 -A)
rm "$tmpfile"

curl -X POST "http://127.0.0.1:6550/test" \
  -H "Timestamp: ${timestamp_b64}" \
  -H "Nonce: ${nonce_b64}" \
  -H "Signature: ${signature}" \
  -H "Content-Type: application/text" \
  --data-binary "Hello, world!"
```
