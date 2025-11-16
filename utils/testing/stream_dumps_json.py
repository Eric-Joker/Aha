# 由deepseek生成。

import asyncio
from collections.abc import AsyncGenerator, AsyncIterable
import inspect
import random
import sys
import tracemalloc
from typing import Any

from orjson import loads as json_loads
from orjson import dumps as json_dumps


sys.setrecursionlimit(10000000)
bytea = bytes(1)


def _try_dumps(obj):
    if obj is None:
        return b"null"
    elif isinstance(obj, bool):
        return b"true" if obj else b"false"
    elif isinstance(obj, int):
        return str(obj).encode("utf-8")
    try:
        return json_dumps(obj)
    except TypeError:
        return


async def stream_async_json(obj):
    if result := _try_dumps(obj):
        yield result
        return

    elif isinstance(obj, dict):
        if not obj:
            yield b"{}"
            return

        first, result, async_gen_items = True, bytearray(b"{"), []
        for key, value in obj.items():
            if json := _try_dumps(value):
                if not first:
                    result.append(44)  # ,
                first = False
                result.extend(json_dumps(key))
                result.append(58)  # :
                result.extend(json)
            else:
                async_gen_items.append((key, value))

        if async_gen_items:
            for key, value in async_gen_items:
                if not first:
                    result.append(44)  # ,
                result.extend(json_dumps(key))
                result.append(58)  # :
                yield result
                result = bytearray()

                async for chunk in stream_async_json(value):
                    yield chunk
                first = False
        else:
            yield result

        yield b"}"

    elif isinstance(obj, (list, tuple, set)):
        if not obj:
            yield b"[]"
            return

        first, result = True, bytearray(b"[")
        for value in obj:
            if json := _try_dumps(value):
                if not first:
                    result.append(44)  # ,
                result.extend(json)
            else:
                if first:
                    yield result
                    result = bytearray()
                elif result:
                    result.append(44)  # ,
                    yield result
                    result = bytearray()
                else:
                    yield b","
                async for chunk in stream_async_json(value):
                    yield chunk
            first = False
        if result:
            result.append(93)  # ]
            yield result
        else:
            yield b"]"

    elif isinstance(obj, AsyncIterable):
        yield b'"'
        async for chunk in obj:
            yield chunk
        yield b'"'

    else:
        yield json_dumps(obj)


async def collect_async_generator(async_gen: AsyncGenerator[bytes, None]):
    """收集异步生成器的所有输出"""
    a = bytearray()
    async for chunk in async_gen:
        a.extend(chunk)
    return a.decode()


async def async_gen():
    for _ in range(1):
        yield bytea


def generate_nested_structure(depth: int, width: int, with_async_gen: bool = False, allow_str=False) -> Any:
    """生成嵌套结构"""
    if depth <= 0:
        return "leaf_string" if random.random() < 0.25 else {}
    if allow_str and random.random() < 0.9:
        return async_gen() if with_async_gen and random.random() < 0.01 else "乐" * random.randint(1, 2)
    elif random.random() < 0.5:
        return {f"{i}": generate_nested_structure(depth - 1, width, with_async_gen, True) for i in range(width)}
    else:
        return [generate_nested_structure(depth - 1, width, with_async_gen, True) for _ in range(width)]


async def benchmark_serialization(data, func, name):
    """基准测试函数"""
    print(f"\n=== 测试 {name} ===")

    # 预热运行
    await collect_async_generator(func(data))

    # 内存使用测试
    tracemalloc.start()
    result = await collect_async_generator(func(data))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"峰值内存使用: {peak / 1024:.2f} KB")

    return {"peak_memory_kb": peak / 1024, "result": result}


async def run_benchmarks():
    """运行所有基准测试"""
    test_cases = [
        ("包含异步生成器的嵌套结构", generate_nested_structure(25, 15, True)),
    ]

    print("生成完了")

    results = {}

    for name, data in test_cases:
        print(f"\n{'='*50}")
        print(f"测试用例: {name}")
        print(f"{'='*50}")

        # 测试方案一
        result_v1 = await benchmark_serialization(data, stream_async_json, "方案一")

        # 使用orjson加载验证有效性
        remove_async_generators(data, value := json_loads(result_v1["result"]))
        try:
            results_consistent = value == data
        except Exception as e:
            results_consistent = e
        results[name] = results_consistent or find_diff(value, data)

    return results


def find_diff(a, b, path=""):
    if a.__class__ != b.__class__:
        return f"类型不同: {a.__class__.__name__} vs {b.__class__.__name__} at {path}"

    if isinstance(a, dict):
        if set(a) != set(b):
            missing = set(a) - set(b)
            extra = set(b) - set(a)
            return f"键不同 at {path}: 缺失{missing} 多余{extra}"
        for k in a:
            result = find_diff(a[k], b[k], f"{path}.{k}" if path else k)
            if result:
                return result

    elif isinstance(a, list):
        if len(a) != len(b):
            return f"长度不同: {len(a)} vs {len(b)} at {path}"
        for i, (x, y) in enumerate(zip(a, b)):
            if result := find_diff(x, y, f"{path}[{i}]"):
                return result

    elif a != b:
        return f"值不同: {a} vs {b} at {path}"

    return None


def remove_async_generators(a, b) -> None:
    """
    递归遍历两个结构相同的嵌套字典/列表，如果a中的值是异步生成器，则从两个对象中删除该元素

    参数:
        a: 第一个嵌套字典或列表
        b: 第二个嵌套字典或列表，结构与a相同
    """
    if isinstance(a, dict):
        # 收集需要删除的键
        keys_to_remove = []
        for key in a:
            if key in b:  # 确保两个字典有相同的键
                if inspect.isasyncgen(a[key]):
                    keys_to_remove.append(key)
                elif isinstance(a[key], (dict, list)) and isinstance(b[key], (dict, list)):
                    # 递归处理嵌套结构
                    remove_async_generators(a[key], b[key])

        # 删除标记的键
        for key in keys_to_remove:
            del a[key]
            del b[key]

    elif isinstance(a, list):
        # 收集需要删除的索引
        indices_to_remove = []
        for i in range(len(a)):
            if i < len(b):  # 确保b有相同的索引
                if inspect.isasyncgen(a[i]):
                    indices_to_remove.append(i)
                elif isinstance(a[i], (dict, list)) and isinstance(b[i], (dict, list)):
                    # 递归处理嵌套结构
                    remove_async_generators(a[i], b[i])

        # 从后向前删除索引，避免索引变化
        indices_to_remove.sort(reverse=True)
        for i in indices_to_remove:
            del a[i]
            del b[i]


async def main():
    """主函数"""
    print("开始性能基准测试...")
    print(await run_benchmarks())


if __name__ == "__main__":
    asyncio.run(main())
