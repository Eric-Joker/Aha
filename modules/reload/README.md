# 重载

super 用户发送 `【前缀】重载` 触发。

在 debug 模式下会从 CPython 层面重载所有模块，并触发 cleanup 和 start 回调。该操作不具备任何线程安全性。

非 debug 模式会自动重启整个 Aha 进程。
