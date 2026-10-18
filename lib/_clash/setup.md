# Clash 代理环境操作

## 组成

| 路径 | 作用 |
|---|---|
| `clash-for-linux.tar.gz` | 外来 Clash 子项目的离线归档 |
| `setup.sh` | 校验、解压和 source 检验包装器 |
| `clash-for-linux/` | 解压后的外来组件，按需生成 |

`clash-for-linux/` 的实现和项目说明由上游维护，本仓库只维护归档与包装入口。

## 只检查

已解压时先执行：

```bash
bash lib/_clash/setup.sh --check
```

检查内容包括：

1. `clash-for-linux/env.sh` 是否存在且可读。
2. `bash -n` 语法检查。
3. 子 Shell source 后是否设置代理变量。
4. 是否提供 `clash_env_proxy_show` 与 `clash_env_proxy_test`。

`source lib/_clash/setup.sh` 只会定义函数，不会自动运行检查。要执行检查，应使用 `bash ... --check`。

## 解压或刷新

```bash
bash lib/_clash/setup.sh
```

脚本先验证 tar 归档完整性，再执行：

```bash
tar -xzf clash-for-linux.tar.gz -C lib/_clash
```

目标目录已存在时采用增量覆盖，不先删除旧目录。上游删掉的文件可能残留。需要完全干净副本时，应先把旧目录移到仓库外或其他可恢复位置，再重新解压。

## 启用代理

`setup.sh` 在直接执行时会 source 解压后的 `env.sh`，代理变量只对执行该脚本的进程有效。脚本结束后，父交互 Shell 不会继承变量。

在需要代理的当前 Shell 中执行：

```bash
source lib/_clash/clash-for-linux/env.sh
env | grep -iE '^(http|https|all|no)_proxy='
```

新版 `env.sh` 可用时：

```bash
clash_env_proxy_show
clash_env_proxy_test
```

`clash_env_proxy_test` 返回非零可能表示代理端口未启动、外网不可达或测试工具缺失。`setup.sh` 把连通性失败视为警告，只要变量已设置仍返回成功。

## 测试参数

包装脚本支持透传：

```bash
CLASH_ENV_TEST_URL=https://example.com \
CLASH_ENV_TEST_TIMEOUT=10 \
bash lib/_clash/setup.sh --check
```

代理环境会影响下载、Git、agent 和包管理器。调试网络问题时先确认 `no_proxy`，避免把内部地址错误发往代理。

## 验证

```bash
bash -n lib/_clash/setup.sh
tar -tzf lib/_clash/clash-for-linux.tar.gz >/dev/null
bash lib/_clash/setup.sh --check
```

只做验证时不执行默认解压流程，避免覆盖现有外来组件目录。
