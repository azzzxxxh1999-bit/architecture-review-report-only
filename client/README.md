# Plus 轻量客户端

这是公开免费仓库中的可选连接器，不包含 Plus Skill、方案算法或修复桥接核心。它只会读取本机审计摘要、兑换授权、接收任务，并调用用户自己的本地 Agent 修复。

```text
python client/plus_client.py --endpoint https://your-worker.workers.dev \
  --root D:/your-project --state D:/your-project/.codemap/modules.json \
  --invite ONE_TIME_CODE --plan short-term \
  --agent-command "codex exec --full-auto --prompt-file %ARCHITECTURE_REPAIR_TASK_FILE%"
```

上传字段只有模块 ID、分数、等级、严重度、标签、代码行数和项目哈希；不会上传路径、源码、源码片段或差异。
