# API

在 `core.api` 模块中存在一个 `API` 类，获取该类本身的属性时会返回用于将调用转发到适配器实例的静态方法，调用该方法即调用 API。

适配器不会实现所有方法，届时会抛出 `NotImplementedError` 异常。

API 返回异常时会抛出 `models.exc.APIException`，其 `code` 属性为 API 返回的异常码，`err_msg` 属性为 API 返回的异常信息。

[示例](../基本教学.md#调用-api)

## APIs

- [Message 有关 API](./Message%20有关%20API.md)
- [Account 有关 API](./Account%20有关%20API.md)
- [Group 有关 API](./Group%20有关%20API.md)
- [Private 有关 API](./Private%20有关%20API.md)
- [Support 有关 API](./Support%20有关%20API.md)

## 指定 Bot 实例

> 一个 Aha 进程可以同时对接多个协议服务，也就诞生了跨协议服务进行 API 调用的需求。

`core.api.API` 的每个静态方法均有一个 `bot` 关键字参数，接受适配器实例的 ID。若未传入，则自动从事件上下文中获取当前的适配器实例。

在 `core.api` 中提供了一个 `select_bot` 异步方法，通过其可以实现依据特定策略选择适配器实例并返回 ID。该方法线程安全。

### 选择策略

策略存在于 `core.api.SS`（Selector Strategy）枚举类中，每个策略都有自己的所需的关键字参数。

当未提供`群组 ID`、`用户 ID`、`平台`参数且策略需要时，会从当前事件上下文中获取。可以通过 `event` 参数指定[事件](../../数据结构/事件对象.md)。

> 对于 `PREFS`、`NTH`、`UNORDERED_NTH` 和 `RANDOM` 策略，若业务逻辑处理十分耗时，建议提前通过 `select_bot` 方法选择出适配器实例，避免事件实例在缓存器中被清理。

<table>
  <tr>
    <th>策略</th>
    <th>说明</th>
    <th>参数</th>
  </tr>
  <tr>
    <td>PREFS</td>
    <td>若<a heaf="../统一配置系统.md">配置</a>项 <code>aha.bot_prefs</code> 为 0 则随机选择接收到相同事件的实例，否则将收到消息的实例按<a heaf="../统一配置系统.md">配置</a>中 <code>bots</code> 键值顺序排序后选择第 <code>aha.bot_prefs</code> 个。</td>
    <td>
      <table>
        <tr>
          <th>参数名</th>
          <th>说明</th>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>NTH</td>
    <td>按 <code>bots</code> 配置顺序排序的接收到相同事件的第 n 个实例。</td>
    <td>
      <table>
        <tr>
          <td>index</td>
          <td>n-1，默认为第一个实例。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>UNORDERED_NTH</td>
    <td>第 n 个接收到相同事件的实例。</td>
    <td>
      <table>
        <tr>
          <td>index</td>
          <td>n-1，默认为第一个也就是最快的那一个实例。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>RANDOM</td>
    <td>接收到相同事件的随机实例。</td>
    <td></td>
  </tr>
  <tr>
    <td>PLATFORM</td>
    <td>若<a heaf="../统一配置系统.md">配置</a>项 <code>aha.bot_prefs</code> 为 0 则随机选择相同平台的可用实例，否则将相同平台的可用实例按<a heaf="../统一配置系统.md">配置</a>中 <code>bots</code> 键值顺序排序后选择第 <code>aha.bot_prefs</code> 个。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>PLATFORM_NTH</td>
    <td>指定平台的第n个可用实例（基于配置文件顺序）。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
        <tr>
          <td>index</td>
          <td>n-1，默认为第一个。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>PLATFORM_RANDOM</td>
    <td>指定平台的随机可用实例。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>PREFS_ANY</td>
    <td>若<a heaf="../统一配置系统.md">配置</a>项 <code>aha.bot_prefs</code> 为 0 则选择随机可用实例，否则选择指向的实例。</td>
    <td>
    </td>
  </tr>
  <tr>
    <td>NTH_ANY</td>
    <td>第几个bot实例（基于配置文件顺序）。</td>
    <td>
      <table>
        <tr>
          <td>index</td>
          <td>n-1，默认为第一个。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>RANDOM_ANY</td>
    <td>随机可用实例。</td>
    <td></td>
  </tr>
  <tr>
    <td>FRIEND</td>
    <td><a heaf="../统一配置系统.md">配置</a>项 <code>aha.cache_conv</code> 为 <code>true</code> 时可用。若<a heaf="../统一配置系统.md">配置</a>项 <code>aha.bot_prefs</code> 为 0 则随机选择有指定好友的可用实例，否则将有指定好友的可用实例按<a heaf="../统一配置系统.md">配置</a>中 <code>bots</code> 键值顺序排序后选择第 <code>aha.bot_prefs</code> 个。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
        <tr>
          <td>conv_id</td>
          <td>指定的好友平台 ID。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>FRIEND_NTH</td>
    <td><a heaf="../统一配置系统.md">配置</a>项 <code>aha.cache_conv</code> 为 <code>true</code> 时可用。指定平台的有指定好友的第n个实例。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
        <tr>
          <td>conv_id</td>
          <td>指定的好友平台 ID。</td>
        </tr>
        <tr>
          <td>index</td>
          <td>n-1，默认为第一个。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>FRIEND_RANDOM</td>
    <td><a heaf="../统一配置系统.md">配置</a>项 <code>aha.cache_conv</code> 为 <code>true</code> 时可用。指定平台的有指定好友的随机实例。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
        <tr>
          <td>conv_id</td>
          <td>指定的好友平台 ID。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>GROUP</td>
    <td><a heaf="../统一配置系统.md">配置</a>项 <code>aha.cache_conv</code> 为 <code>true</code> 时可用。若<a heaf="../统一配置系统.md">配置</a>项 <code>aha.bot_prefs</code> 为 0 则随机选择有指定群组的可用实例，否则将有指定群组的可用实例按<a heaf="../统一配置系统.md">配置</a>中 <code>bots</code> 键值顺序排序后选择第 <code>aha.bot_prefs</code> 个。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
        <tr>
          <td>conv_id</td>
          <td>指定的平台群组 ID。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>GROUP_NTH</td>
    <td><a heaf="../统一配置系统.md">配置</a>项 <code>aha.cache_conv</code> 为 <code>true</code> 时可用。指定平台的有指定群组的第n个实例。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
        <tr>
          <td>conv_id</td>
          <td>指定的平台群组 ID。</td>
        </tr>
        <tr>
          <td>index</td>
          <td>n-1，默认为第一个。</td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td>GROUP_RANDOM</td>
    <td><a heaf="../统一配置系统.md">配置</a>项 <code>aha.cache_conv</code> 为 <code>true</code> 时可用。指定平台的有指定群组的随机实例。</td>
    <td>
      <table>
        <tr>
          <td>platform</td>
          <td>平台。</td>
        </tr>
        <tr>
          <td>conv_id</td>
          <td>指定的平台群组 ID。</td>
        </tr>
      </table>
    </td>
  </tr>
</table>
