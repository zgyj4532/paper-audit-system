#!/bin/bash
# ============================================================
# AI Auditor Engine-Java 一键启动脚本
# 适用：Linux 服务器 / Mac 本地
# 用法：chmod +x start.sh && ./start.sh
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${BLUE}"
    echo "============================================================"
    echo "   AI Auditor Engine-Java 启动工具"
    echo "============================================================"
    echo -e "${NC}"
}

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warn()    { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error()   { echo -e "${RED}❌ $1${NC}"; }
print_info()    { echo -e "${BLUE}ℹ️  $1${NC}"; }

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装。请先安装 Docker："
        echo "  Ubuntu: sudo apt install docker.io docker-compose-plugin"
        echo "  Mac:    https://www.docker.com/products/docker-desktop"
        exit 1
    fi
    if ! docker info &> /dev/null; then
        print_error "Docker 守护进程未运行，请先启动 Docker。"
        exit 1
    fi
    print_success "Docker 已就绪"
}

check_java() {
    if ! command -v java &> /dev/null; then
        print_error "Java 未安装。请安装 Java 21："
        echo "  Ubuntu: sudo apt install openjdk-21-jdk"
        exit 1
    fi
    JAVA_VER=$(java -version 2>&1 | head -1 | grep -oP '(?<=version ")[^"]+' | cut -d. -f1)
    if [ "$JAVA_VER" -lt 21 ] 2>/dev/null; then
        print_warn "当前 Java 版本为 $JAVA_VER，建议使用 Java 21+"
    else
        print_success "Java $JAVA_VER 已就绪"
    fi
}

wait_for_service() {
    local name=$1
    local host=$2
    local port=$3
    local max_wait=60
    local waited=0
    echo -n "  等待 $name 就绪"
    while ! nc -z "$host" "$port" 2>/dev/null; do
        sleep 2
        waited=$((waited + 2))
        echo -n "."
        if [ $waited -ge $max_wait ]; then
            echo ""
            print_error "$name 启动超时（${max_wait}s）"
            return 1
        fi
    done
    echo ""
    print_success "$name 已就绪（${host}:${port}）"
}

print_banner

echo "请选择启动模式："
echo ""
echo "  1) 本地模式（mvn spring-boot:run）"
echo "     - 无需 Docker，使用 H2 内嵌数据库"
echo "     - 适合：快速开发调试"
echo ""
echo "  2) Docker 完整模式（PostgreSQL + Redis + Java 引擎）"
echo "     - 与生产环境完全一致"
echo "     - 适合：联调测试、服务器部署"
echo ""
echo "  3) 仅启动基础设施（PostgreSQL + Redis）"
echo "     - 配合 mvn spring-boot:run -Dspring-boot.run.profiles=docker 使用"
echo ""
echo "  4) 运行所有单元测试"
echo ""
echo "  5) 停止所有 Docker 容器"
echo ""
echo "  6) 查看服务日志"
echo ""
read -p "请输入选项 (1-6): " choice

case $choice in
    1)
        print_info "本地模式启动..."
        check_java
        echo ""
        print_info "服务启动后访问：http://localhost:8081"
        print_info "gRPC 端口：localhost:9191"
        echo ""
        mvn spring-boot:run
        ;;
    2)
        print_info "Docker 完整模式启动..."
        check_docker
        echo ""
        print_info "构建镜像并启动所有服务（首次约需 3-5 分钟）..."
        docker-compose up --build -d
        echo ""
        wait_for_service "PostgreSQL" "localhost" "5432"
        wait_for_service "Redis" "localhost" "6379"
        wait_for_service "Java 引擎 HTTP" "localhost" "8081"
        wait_for_service "Java 引擎 gRPC" "localhost" "9191"
        echo ""
        echo -e "${GREEN}============================================================"
        echo "  🚀 所有服务已启动！"
        echo ""
        echo "  HTTP 接口：  http://localhost:8081"
        echo "  gRPC 端口：  localhost:9191"
        echo "  PostgreSQL： localhost:5432"
        echo "               用户: auditor_user / 密码: auditor_pass_2024"
        echo "  Redis：      localhost:6379"
        echo "               密码: auditor_redis_2024"
        echo "============================================================"
        echo -e "${NC}"
        ;;
    3)
        print_info "启动基础设施（PostgreSQL + Redis）..."
        check_docker
        docker-compose up -d postgres redis
        echo ""
        wait_for_service "PostgreSQL" "localhost" "5432"
        wait_for_service "Redis" "localhost" "6379"
        echo ""
        print_success "基础设施已就绪！"
        print_info "现在可以运行："
        echo "  mvn spring-boot:run -Dspring-boot.run.profiles=docker"
        ;;
    4)
        print_info "运行所有单元测试..."
        check_java
        mvn clean test
        ;;
    5)
        print_info "停止所有 Docker 容器..."
        docker-compose down
        print_success "已停止。数据已保存在 Docker Volume 中。"
        ;;
    6)
        print_info "查看 engine-java 服务日志（Ctrl+C 退出）..."
        docker-compose logs -f engine-java
        ;;
    *)
        print_error "无效选项：$choice"
        exit 1
        ;;
esac
