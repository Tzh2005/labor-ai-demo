# 贡献与变更流程

## 开始前

1. 在 `项目工程化/01-产品管理/需求池.md` 找到或新增需求。
2. 在 `项目工程化/02-项目管理/迭代计划.md` 登记目标、负责人和验收标准。
3. 涉及架构、数据、依赖或安全的变更，先更新对应设计文档。

## 开发要求

- 从 `main` 创建短生命周期分支：`feature/<id>-<short-name>` 或 `fix/<id>-<short-name>`。
- 不提交 `.env`、数据库、Chroma索引、模型缓存和日志。
- 用户输入、检索文档和模型输出都视为不可信边界，必须经过现有安全处理。
- 新行为必须有自动化测试或在测试清单中说明手工验证方式。

## 提交前

```powershell
python -m py_compile app.py ai_service.py conversation_store.py knowledge_base.py check_environment.py
python -m unittest discover -s tests -v
python -m pip check
```

然后执行 `项目工程化/06-测试质量/发布前检查清单.md`，在合并请求中附上结果和风险。

## 合并规则

- 标题使用动词开头，说明行为和原因。
- 一个合并请求只解决一个可验证目标。
- 至少一名技术/测试评审者批准；P0/P1、安全和数据结构变更需要技术负责人批准。
- 合并后删除分支，发布说明记录用户可感知变化和回滚方式。
