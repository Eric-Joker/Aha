# 已有适配器

- <span style="font-size: 1.5em;">[**NapCat**](./NapCat.md)：与 [NapCat](https://github.com/NapNeko/NapCatQQ) 对接的适配器。</spam>
- <span style="font-size: 1.5em;">[**FastAPI**](./FastAPI.md)：建立 [FastAPI](https://github.com/fastapi/fastapi) 服务器，将请求通过 [External 事件](../模块开发/订阅与发布事件.md) 上报。</spam>
- <span style="font-size: 1.5em;">未完待续。</spam>

## 配置示例

```yaml
bots:
- NapCat:
    uri: ws://127.0.0.1:5325
    token: '~!@#$%^&*()_+'
    start_server_command: 'napcat restart 123456'
    retry_config:
      wait_exponential:
        multiplier: 1
        max: 30
        exp_base: 2
        min: 1
- FastAPI:
    host: 0.0.0.0
    port: 6550
```
