@echo off
chcp 65001 >nul
echo ========================================
echo   劳务派遣AI客服Demo - 一键部署脚本
echo ========================================
echo.

:: 检查是否在正确的目录
if not exist "app.py" (
    echo [错误] 请在labor-ai-demo目录下运行此脚本！
    pause
    exit /b 1
)

:: 认证密码必须由启动环境注入，脚本不保存或生成默认密码
if "%DEMO_PASSWORD%"=="" (
    echo [错误] 未设置 DEMO_PASSWORD。请先在当前终端执行：
    echo   set "DEMO_PASSWORD=请替换为随机长密码"
    pause
    exit /b 1
)

:: 已构建过索引时启用离线模式，避免 HuggingFace 联网检查卡顿（首次部署不设置，以便下载模型）
if exist "chroma_db\.data_signature" (
    set HF_HUB_OFFLINE=1
    echo [提示] 检测到本地索引，已启用离线模式（跳过 HuggingFace 联网检查）
)

:: 确保本机请求不走系统代理（Clash 等开启时 httpx 会误走代理，导致问答超时或 502）
set "NO_PROXY=localhost,127.0.0.1,%NO_PROXY%"
set "no_proxy=%NO_PROXY%"

echo [步骤1/7] 检查Python安装...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python，请先安装Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [✓] Python已安装

echo.
echo [步骤2/7] 检查Ollama安装...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到Ollama
    echo.
    echo 请先安装Ollama:
    echo 1. 访问: https://ollama.com/download/windows
    echo 2. 下载并安装OllamaSetup.exe
    echo 3. 安装完成后，关闭所有终端，重新运行此脚本
    echo.
    pause
    exit /b 1
)
echo [✓] Ollama已安装

echo.
echo [步骤3/7] 检查Ollama服务...
curl -s http://localhost:11434 >nul 2>&1
if errorlevel 1 (
    echo [警告] Ollama服务未运行
    echo [操作] 正在启动Ollama服务...
    start "Ollama Service" cmd /c "ollama serve"
    timeout /t 3 >nul
    echo [✓] Ollama服务已启动（后台窗口请保持打开）
) else (
    echo [✓] Ollama服务正在运行
)

echo.
echo [步骤4/7] 检查AI模型...
:: 支持通过 OLLAMA_MODEL 环境变量切换模型（如 setx OLLAMA_MODEL qwen2.5:7b），默认 qwen2.5:3b（本地 CPU 响应更快）
set "AI_MODEL=%OLLAMA_MODEL%"
if "%AI_MODEL%"=="" set "AI_MODEL=qwen2.5:3b"
ollama list | findstr "%AI_MODEL%" >nul 2>&1
if errorlevel 1 (
    echo [警告] 模型 %AI_MODEL% 未下载
    echo.
    choice /C YN /M "是否现在下载模型 %AI_MODEL%（3b约1.9GB，7b约4.7GB）"
    if errorlevel 2 (
        echo [跳过] 请手动运行: ollama pull %AI_MODEL%
        echo 或使用小模型: ollama pull qwen2.5:3b（速度更快）
        pause
        exit /b 1
    )
    echo [操作] 正在下载模型，请稍候...
    ollama pull %AI_MODEL%
    if errorlevel 1 (
        echo [错误] 模型下载失败
        pause
        exit /b 1
    )
    echo [✓] 模型下载完成
) else (
    echo [✓] 模型 %AI_MODEL% 已存在
)

echo.
echo [步骤5/7] 安装Python依赖...
if not exist "venv" (
    echo [操作] 创建虚拟环境...
    python -m venv venv
    echo [✓] 虚拟环境已创建
)

echo [操作] 激活虚拟环境并安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [警告] 使用清华源安装失败，尝试默认源...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
)
echo [✓] 依赖安装完成

echo.
echo [步骤6/7] 运行本地环境预检...
python check_environment.py --build-index
if errorlevel 1 (
    echo [错误] 本地环境预检未通过，请根据上面的提示处理后再试。
    pause
    exit /b 1
)
echo [✓] 本地环境预检通过

echo.
echo [步骤7/7] 启动Demo...
echo.
echo ========================================
echo   🎉 准备工作完成，正在启动Demo...
echo ========================================
echo.
echo 浏览器将自动打开: http://localhost:8501
echo.
echo 测试问题：
echo   - 有什么普工岗位？
echo   - 石岩电子厂工资多少？
echo   - 松岗制衣厂包吃包住吗？（福利区分）
echo.
echo 按 Ctrl+C 可停止服务
echo.

streamlit run app.py

pause
