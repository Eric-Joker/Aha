## 整体概览

1. **启动阶段**：框架初始化、加载配置、启动服务、加载模块并调用模块的 `on_start` 回调。
2. **运行阶段**：事件循环等待并分发[事件](./订阅与发布事件.md)，模块回调被触发，可调用 API 与平台交互。
3. **关闭阶段**：收到终止信号后，调用所有模块的 `on_cleanup` 回调，然后释放资源。

```mermaid
sequenceDiagram
    participant Core as 核心框架
    participant Adapter as 适配器（Bot实例）
    participant Platform as 协议框架服务
    participant Dispatcher as 事件分发器
    participant API as API 调用路由
    participant Loader as 模块加载器
    participant Module as 模块（回调函数）

    %% 启动阶段
    Core->>Core: 初始化配置
    Core->>Loader: 扫描并加载模块
    Loader->>Module: 导入模块，装饰器收集回调
    Core->>Core: 初始化数据库等基础组件
    Core->>Adapter: 启动所有 Bot 实例
    Adapter->>Platform: 连接协议框架服务
    Adapter-->>Core: 全部 Bot 实例初始化完毕，就绪
    Core->>Core: 初始化计划任务等工具服务
    Core->>Module: 调用 on_start 注册的回调

    %% 运行阶段
    Adapter->>Adapter: 监听平台事件
    Adapter-->>Dispatcher: 上报事件（Message/Notice/Request等）
    Dispatcher->>Dispatcher: 去重、预处理
    Dispatcher->>Module: 条件匹配并调用回调
    Module->>API: 在回调中调用 API（如发送消息）
    API->>API: 根据策略选择 Bot 实例（默认与事件上下文相同实例）
    API->>Adapter: 向选中的 Bot 发送请求
    Adapter-->>Platform: 与平台交互

    %% 关闭阶段
    Core->>Core: 收到终止信号（SIGINT/SIGTERM）
    Core->>Module: 调用 on_cleanup 注册的回调
    Core->>Adapter: 关闭所有 Bot 实例
    Core->>Core: 释放资源（数据库、调度器等）
```

## 模块生命周期

一个 Aha 模块的生命周期包含以下阶段：

- **加载**：模块被导入：注册配置、装饰器注册回调等。
- **就绪**：框架完成全部启动流程，调用通过 `core.dispatcher.on_start` 注册的回调函数。
- **运行**：事件触发模块的回调，模块通过 API 与平台交互。
- **卸载**：框架收到终止运行请求时，调用通过 `core.dispatcher.on_cleanup` 注册的回调函数。
