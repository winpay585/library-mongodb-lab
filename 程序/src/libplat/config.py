"""配置加载模块。

所有路径以项目根目录为基准解析，连接串集中在 config.ini，
支持环境变量覆盖，便于换机器后直接运行。
"""
from __future__ import annotations

import configparser
import os
from pathlib import Path

# 项目根目录: src/libplat/config.py -> 上两级
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings:
    """封装 config.ini 的读取结果。"""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = Path(
            os.environ.get("LIB_CONFIG") or (BASE_DIR / "config.ini")
        )
        self.parser = configparser.ConfigParser()
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        self.parser.read(self.config_path, encoding="utf-8")

    # ---- 基础参数 ----
    @property
    def db_name(self) -> str:
        return os.environ.get("LIB_DB") or self.parser.get("app", "db_name", fallback="library")

    @property
    def profile(self) -> str:
        return os.environ.get("LIB_PROFILE") or self.parser.get("app", "default_profile", fallback="standalone")

    @property
    def page_size(self) -> int:
        return self.parser.getint("app", "page_size", fallback=10)

    # ---- 连接串 ----
    def uri(self, profile: str | None = None, auth: bool = True) -> str:
        """返回指定形态的连接串。

        auth=True 时优先取 auth_uri；若未配置则回退到 uri（未开启访问控制的阶段）。
        """
        profile = profile or self.profile
        env_uri = os.environ.get("LIB_URI")
        if env_uri:
            return env_uri
        if not self.parser.has_section(profile):
            raise KeyError(f"config.ini 缺少 [{profile}] 段落")
        if auth:
            value = self.parser.get(profile, "auth_uri", fallback=None)
            if value:
                return value
        return self.parser.get(profile, "uri")

    @property
    def readonly_uri(self) -> str:
        return os.environ.get("LIB_READONLY_URI") or self.parser.get("standalone", "readonly_uri")

    @property
    def read_preference(self) -> str:
        return self.parser.get(self.profile, "read_preference", fallback="primary")

    # ---- 路径 ----
    def path(self, key: str) -> Path:
        rel = self.parser.get("paths", key)
        return (BASE_DIR / rel).resolve()

    # ---- 数据文件 ----
    @property
    def source_files(self) -> dict[str, Path]:
        base = self.path("data_dir")
        return {
            "books": base / "books.txt",
            "readers": base / "readers.txt",
            "borrow_logs": base / "borrow_logs.txt",
        }

    def describe(self) -> str:
        return (
            f"配置文件: {self.config_path}\n"
            f"部署形态: {self.profile}\n"
            f"数据库名: {self.db_name}\n"
            f"连接串  : {self.uri()}"
        )


settings = Settings()
