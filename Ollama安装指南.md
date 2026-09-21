# 🚀 Ollama 安装指南

## ⚠️ 当前状态
Ollama **未安装**，需要先安装才能继续。

---

## 📥 安装步骤（5分钟）

### Step 1: 下载安装包

**方法A：浏览器下载（推荐）**
1. 打开浏览器
2. 访问：https://ollama.com/download/windows
3. 点击下载 `OllamaSetup.exe`
4. 等待下载完成（约50-100MB）

**方法B：直接下载链接**
```
https://ollama.com/download/OllamaSetup.exe
```

---

### Step 2: 安装Ollama

1. 找到下载的 `OllamaSetup.exe`
2. 双击运行安装程序
3. 按照提示点击"下一步"
4. 选择安装路径（默认即可）
5. 等待安装完成（1-2分钟）
6. 点击"完成"

---

### Step 3: 验证安装

**重要**：安装完成后，**必须关闭所有终端窗口**，然后重新打开。

打开新的终端，运行：
```bash
ollama --version
```

如果看到版本号（如 `ollama version 0.x.x`），说明安装成功！

---

### Step 4: 启动Ollama服务

Ollama安装后会自动启动服务，你可以验证一下：

**Windows方法**：
1. 按 `Win+R` 打开运行
2. 输入：`services.msc`
3. 查找 `Ollama` 服务
4. 确认状态为"正在运行"

**或者在终端运行**：
```bash
ollama list
```

如果能看到空列表（或已有模型列表），说明服务正常运行！

---

## ✅ 完成标准

当你完成以下所有检查，Ollama就安装好了：

- [ ] OllamaSetup.exe 下载完成
- [ ] 安装程序运行完成
- [ ] **关闭并重新打开终端**
- [ ] `ollama --version` 显示版本号
- [ ] `ollama list` 能正常运行

---

## 🐛 常见问题

### 1. 下载速度慢
- 耐心等待，安装包约50-100MB
- 或使用手机热点下载

### 2. 安装后命令找不到
- **必须关闭所有终端窗口**
- 重新打开新终端
- 再运行 `ollama --version`

### 3. 服务未启动
```bash
# 手动启动服务
ollama serve
```
保持这个终端窗口打开，在另一个终端继续操作。

---

## 📋 安装完成后的下一步

完成Ollama安装后，回来告诉我，然后我们继续：

**任务2**: 下载 qwen2.5:7b 模型（4.7GB）
```bash
ollama pull qwen2.5:7b
```

---

## 🎯 现在就开始

1. **立即访问**：https://ollama.com/download/windows
2. **下载** OllamaSetup.exe
3. **安装**（1-2分钟）
4. **重启终端**
5. **回来告诉我** ✅

---

**安装Ollama是最关键的第一步，完成这步后就轻松了！** 💪
