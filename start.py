import shutil
import subprocess
import webbrowser
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    if shutil.which("docker") is None:
        print("Установите и запустите Docker Desktop, затем повторите запуск.")
        return 1
    env = root / "backend" / ".env"
    if not env.exists():
        shutil.copyfile(root / "backend" / ".env.example", env)
        print("Создан backend/.env. Для ответов LLM укажите провайдера, модель и ключ.")
    result = subprocess.run(["docker", "compose", "up", "--build", "-d"], cwd=root)
    if result.returncode == 0:
        print("Приложение: http://localhost:8080")
        webbrowser.open("http://localhost:8080")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
