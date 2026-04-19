@echo off
chcp 65001 > nul
title AI Auditor - Engine Java

echo.
echo ============================================================
echo   AI Auditor Engine-Java 启动工具
echo ============================================================
echo.
echo 请选择启动模式：
echo.
echo   [1] 本地模式（mvn spring-boot:run）
echo       - 无需 Docker，直接运行
echo       - 使用 H2 内嵌数据库（数据重启后清空）
echo       - 适合：快速开发调试、运行单元测试
echo.
echo   [2] Docker 模式（docker-compose up）
echo       - 需要安装 Docker Desktop
echo       - 使用真实 PostgreSQL + Redis（数据持久化）
echo       - 与服务器环境完全一致，推荐联调时使用
echo.
echo   [3] 仅启动基础设施（PostgreSQL + Redis，不启动 Java）
echo       - 适合：想用 mvn spring-boot:run 但需要真实数据库时
echo.
echo   [4] 运行所有单元测试
echo.
echo   [5] 停止所有 Docker 容器
echo.
echo   [Q] 退出
echo.

set /p choice=请输入选项 (1/2/3/4/5/Q): 

if /i "%choice%"=="1" goto local_mode
if /i "%choice%"=="2" goto docker_mode
if /i "%choice%"=="3" goto infra_only
if /i "%choice%"=="4" goto run_tests
if /i "%choice%"=="5" goto stop_docker
if /i "%choice%"=="Q" goto end
if /i "%choice%"=="q" goto end

echo 无效选项，请重新运行。
pause
goto end

:local_mode
echo.
echo [本地模式] 启动中...
echo 提示：服务启动后访问 http://localhost:8081
echo       gRPC 端口：localhost:9191
echo.
mvn spring-boot:run
goto end

:docker_mode
echo.
echo [Docker 模式] 构建并启动所有服务...
echo 首次启动需要下载镜像，约需 3-5 分钟，请耐心等待。
echo.
docker-compose up --build -d
if %errorlevel% neq 0 (
    echo.
    echo [错误] Docker Compose 启动失败！
    echo 请确认 Docker Desktop 已启动，然后重试。
    pause
    goto end
)
echo.
echo [等待服务就绪] 约 30 秒...
timeout /t 30 /nobreak > nul
echo.
echo ============================================================
echo   服务已启动！
echo.
echo   HTTP 接口：  http://localhost:8081
echo   gRPC 端口：  localhost:9191
echo   PostgreSQL： localhost:5432 (用户: auditor_user / 密码: auditor_pass_2024)
echo   Redis：      localhost:6379 (密码: auditor_redis_2024)
echo.
echo   查看日志：docker-compose logs -f engine-java
echo   停止服务：运行本脚本选择 [5]
echo ============================================================
echo.
pause
goto end

:infra_only
echo.
echo [基础设施模式] 仅启动 PostgreSQL + Redis...
docker-compose up -d postgres redis
if %errorlevel% neq 0 (
    echo [错误] 启动失败，请确认 Docker Desktop 已启动。
    pause
    goto end
)
echo.
echo [等待数据库就绪] 约 15 秒...
timeout /t 15 /nobreak > nul
echo.
echo ============================================================
echo   基础设施已启动！
echo.
echo   PostgreSQL： localhost:5432 (用户: auditor_user / 密码: auditor_pass_2024)
echo   Redis：      localhost:6379 (密码: auditor_redis_2024)
echo.
echo   现在可以运行：mvn spring-boot:run -Dspring-boot.run.profiles=docker
echo   （使用 docker profile 连接真实数据库）
echo ============================================================
echo.
pause
goto end

:run_tests
echo.
echo [测试模式] 运行所有单元测试...
echo.
mvn clean test
echo.
echo 测试完成！
pause
goto end

:stop_docker
echo.
echo [停止] 正在停止所有 Docker 容器...
docker-compose down
echo 已停止。数据已保存在 Docker Volume 中，下次启动不会丢失。
pause
goto end

:end
