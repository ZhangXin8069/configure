# AGENTS.md — scripts 维护脚本

仓库维护与引导脚本。与 `bin/` 不同，本目录脚本**不自动生成别名**，按路径直接调用。

## 脚本

### script_alias.sh

扫描 `.sh` 文件生成别名文件 `tmp/scripts.sh`：

1. source `env.sh` 建立 `PATH`
2. 向 `tmp/scripts.sh` 写入带时间戳的头部
3. 扫描 `tmp/` 下 `.sh` → 生成 `alias <name>='bash <path>'`
4. 扫描 `bin/` 下 `.sh` → 同上
5. 写入带时间戳的尾部

**bin/ 或 tmp/ 下新增/删除 `.sh` 后必须重跑**，新 shell（或 `source ~/.zshrc`）后生效。

### script_make.sh

测试脚本生成器：在 `tmp/` 生成 `test0.sh`…`test9.sh`（各编译运行对应 `testN.cu` 的 CUDA 文件），用于 GPU 代码开发调试。产物会被自动别名。

## 依赖链

```
scripts/script_alias.sh ──生成──> tmp/scripts.sh ──被source──> env.sh ──被source──> .zshrc
```

`scripts/scripts/` 子目录当前为空，预留给辅助脚本。
