"""IAM-токен DataLens: локальный кэш + выпуск через Yandex Cloud CLI."""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple

from ..config import Settings


class AuthError(RuntimeError):
    """Ошибка получения/обновления IAM-токена."""


def find_yc_executable() -> Optional[str]:
    env_path = os.environ.get("YC_CLI_PATH")
    if env_path:
        p = Path(env_path.strip('"'))
        if p.is_file():
            return str(p)

    yc_name = "yc.exe" if platform.system() == "Windows" else "yc"
    which = shutil.which(yc_name) or shutil.which("yc")
    if which:
        return which

    if platform.system() == "Windows":
        candidates = [
            Path.home() / "yandex-cloud" / "bin" / "yc.exe",
            Path(os.environ.get("USERPROFILE", "")) / "yandex-cloud" / "bin" / "yc.exe",
        ]
    else:
        candidates = [Path.home() / ".yandex-cloud" / "bin" / "yc"]
    for p in candidates:
        if p and p.is_file():
            return str(p)
    return None


def get_cached_token_data(cache_file: Path) -> Tuple[Optional[str], float]:
    try:
        data = json.loads(Path(cache_file).read_text(encoding="utf-8"))
        return data.get("token"), float(data.get("timestamp", 0))
    except (OSError, json.JSONDecodeError, ValueError):
        return None, 0.0


def fetch_new_token(cache_file: Path) -> str:
    exe = find_yc_executable()
    if not exe:
        raise AuthError("YC CLI не найден: задайте YC_CLI_PATH или добавьте yc в PATH.")
    try:
        result = subprocess.run([exe, "iam", "create-token"],
                                capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise AuthError(f"yc iam create-token завершился с ошибкой: {exc.stderr}") from exc
    except FileNotFoundError as exc:
        raise AuthError(f"Не удалось запустить yc: {exc}") from exc

    token = result.stdout.strip()
    if not token:
        raise AuthError("YC CLI вернул пустой токен. Проверьте авторизацию (yc init).")
    Path(cache_file).write_text(
        json.dumps({"token": token, "timestamp": time.time()}), encoding="utf-8")
    return token


def get_iam_token(settings: Settings) -> str:
    env_token = os.environ.get("DATALENS_IAM_TOKEN")
    if env_token:
        return env_token
    token, ts = get_cached_token_data(settings.iam_cache_file)
    if token and time.time() - ts < settings.iam_ttl_seconds:
        return token
    return fetch_new_token(settings.iam_cache_file)


def refresh_iam_token(settings: Settings, used_token: str) -> str:
    token, ts = get_cached_token_data(settings.iam_cache_file)
    fresh = bool(token) and (time.time() - ts < settings.iam_ttl_seconds)
    if fresh and token != used_token and not os.environ.get("DATALENS_IAM_TOKEN"):
        return token  # другой процесс уже обновил токен
    return fetch_new_token(settings.iam_cache_file)