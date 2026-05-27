import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def build_services(api_key, include_weather, no_user):
    services = [
        ("tour_mcp", [sys.executable, "tour_mcp.py"], 8002),
        ("hotel_mcp", [sys.executable, "hotel_mcp.py"], 8003),
        ("coordinator", [sys.executable, "coordinator.py", "--api_key", api_key], 9000),
        ("tour_agent", [sys.executable, "tour_agent.py", "--api_key", api_key], 9020),
        ("hotel_agent", [sys.executable, "hotel_agent.py", "--api_key", api_key], 9030),
    ]

    if include_weather:
        services.insert(0, ("weather_mcp", [sys.executable, "weather_mcp.py"], 8001))
        services.insert(3, ("weather_agent", [sys.executable, "weather_agent.py", "--api_key", api_key], 9010))

    if not no_user:
        services.append(("user", [sys.executable, "user.py"], None))

    return services


def launch_service(name, command, port, new_window):
    creationflags = 0
    if os.name == "nt" and new_window:
        creationflags = subprocess.CREATE_NEW_CONSOLE

    print(f"[MAIN] 启动 {name}" + (f" (port {port})" if port else ""))
    print(f"[MAIN] 命令: {' '.join(command)}")

    return subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        creationflags=creationflags
    )


def stop_processes(processes):
    for name, proc in reversed(processes):
        if proc.poll() is not None:
            continue

        print(f"[MAIN] 正在关闭 {name} ...")
        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.terminate()
        except Exception:
            proc.terminate()

    deadline = time.time() + 5
    for name, proc in reversed(processes):
        if proc.poll() is not None:
            continue

        remaining = max(0.1, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            print(f"[MAIN] {name} 未及时退出，强制结束。")
            proc.kill()


def parse_args():
    parser = argparse.ArgumentParser(description="一键启动旅行社多 Agent 演示系统")
    parser.add_argument(
        "--api_key",
        "-k",
        default=os.environ.get("DEEPSEEK_API_KEY"),
        help="LLM API Key。也可以通过环境变量 DEEPSEEK_API_KEY 提供。"
    )
    parser.add_argument(
        "--include-weather",
        action="store_true",
        help="同时启动原有天气 Agent 和天气 MCP。默认不启动。"
    )
    parser.add_argument(
        "--no-user",
        action="store_true",
        help="不启动 user.py，只启动后台服务。"
    )
    parser.add_argument(
        "--same-window",
        action="store_true",
        help="所有进程共用当前终端输出。Windows 默认会为每个组件打开新控制台。"
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=0.4,
        help="每个进程启动之间的间隔秒数，默认 0.4。"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.api_key:
        print("[MAIN] 缺少 API Key。请使用 python main.py --api_key YOUR_KEY")
        print("[MAIN] 或先设置环境变量 DEEPSEEK_API_KEY。")
        return 2

    new_window = os.name == "nt" and not args.same_window
    services = build_services(args.api_key, args.include_weather, args.no_user)
    processes = []

    print("[MAIN] 即将启动旅行社多 Agent 演示系统")
    print("[MAIN] 默认链路: Coordinator -> tour_agent -> Coordinator -> hotel_agent")
    print("[MAIN] 按 Ctrl+C 可尝试关闭由 main.py 启动的后台进程。")

    try:
        for name, command, port in services:
            proc = launch_service(name, command, port, new_window)
            processes.append((name, proc))
            time.sleep(args.startup_delay)

        print("[MAIN] 所有组件已启动。")
        if new_window and not args.no_user:
            print("[MAIN] 请在 user.py 窗口输入旅行 + 酒店需求进行演示。")
        elif args.no_user:
            print("[MAIN] 已跳过 user.py，可另开终端手动运行 python user.py。")

        while True:
            time.sleep(1)
            stopped = [(name, proc.returncode) for name, proc in processes if proc.poll() is not None]
            if stopped:
                for name, code in stopped:
                    print(f"[MAIN] 检测到 {name} 已退出，返回码 {code}。")
                break

    except KeyboardInterrupt:
        print("\n[MAIN] 收到 Ctrl+C，准备关闭进程。")
    finally:
        stop_processes(processes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
