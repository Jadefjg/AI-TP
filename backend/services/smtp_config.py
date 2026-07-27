from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.db.session import SessionLocal
from backend.models.entities import SystemSetting

SMTP_KEYS = {
    "host": "smtp.host",
    "port": "smtp.port",
    "user": "smtp.user",
    "password": "smtp.password",
    "use_tls": "smtp.use_tls",
    "use_ssl": "smtp.use_ssl",
    "from_addr": "smtp.from",
    "dry_run": "smtp.dry_run",
}


@dataclass(frozen=True)
class SmtpRuntimeConfig:
    host: str
    port: int
    user: str
    password: str
    use_tls: bool
    use_ssl: bool
    from_addr: str
    dry_run: bool
    outbox_dir: str

    @property
    def configured(self) -> bool:
        return bool(self.host.strip())


def _db_map(db: Session | None = None) -> dict[str, str]:
    own = False
    if db is None:
        db = SessionLocal()
        own = True
    try:
        rows = (
            db.query(SystemSetting)
            .filter(SystemSetting.key.in_(list(SMTP_KEYS.values())))
            .all()
        )
        return {row.key: row.value for row in rows}
    finally:
        if own:
            db.close()


def _truthy(raw: str | None, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_smtp_config(db: Session | None = None) -> SmtpRuntimeConfig:
    """Merge SystemSetting overrides on top of env/.env defaults."""
    settings = get_settings()
    stored = _db_map(db)

    def pick(key: str, env_value: str) -> str:
        raw = stored.get(SMTP_KEYS[key])
        if raw is None or raw == "":
            return env_value
        return raw

    port_raw = pick("port", str(settings.smtp_port))
    try:
        port = int(port_raw)
    except ValueError:
        port = settings.smtp_port

    return SmtpRuntimeConfig(
        host=pick("host", settings.smtp_host or "").strip(),
        port=port,
        user=pick("user", settings.smtp_user or ""),
        password=pick("password", settings.smtp_password or ""),
        use_tls=_truthy(stored.get(SMTP_KEYS["use_tls"]), settings.smtp_use_tls),
        use_ssl=_truthy(stored.get(SMTP_KEYS["use_ssl"]), getattr(settings, "smtp_use_ssl", False)),
        from_addr=pick("from_addr", settings.smtp_from or "noreply@example.com").strip()
        or "noreply@example.com",
        dry_run=_truthy(stored.get(SMTP_KEYS["dry_run"]), settings.smtp_dry_run),
        outbox_dir=settings.smtp_outbox_dir or "./data/mail_outbox",
    )


def upsert_smtp_settings(db: Session, payload: dict) -> SmtpRuntimeConfig:
    mapping = {
        "host": ("host", "SMTP 服务器主机"),
        "port": ("port", "SMTP 端口"),
        "user": ("user", "SMTP 用户名"),
        "password": ("password", "SMTP 密码 / 授权码"),
        "use_tls": ("use_tls", "启用 STARTTLS"),
        "use_ssl": ("use_ssl", "启用 SSL（如 465）"),
        "from_addr": ("from_addr", "发件人地址"),
        "dry_run": ("dry_run", "未配置主机时写入本地发件箱"),
    }
    for field, (key, desc) in mapping.items():
        if field not in payload:
            continue
        value = payload[field]
        if field == "password" and (value is None or value == "" or value == "********"):
            # Keep existing password when UI sends masked placeholder.
            continue
        if isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value).strip()
        db_key = SMTP_KEYS[key]
        row = db.query(SystemSetting).filter(SystemSetting.key == db_key).one_or_none()
        if row:
            row.value = text
            row.description = desc
        else:
            db.add(SystemSetting(key=db_key, value=text, description=desc))
    db.commit()
    return resolve_smtp_config(db)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PLACEHOLDER_FROM = {"noreply@example.com", "no-reply@example.com"}


def validate_smtp_ready(cfg: SmtpRuntimeConfig) -> str | None:
    """Return a Chinese hint when SMTP config is clearly not ready for real send."""
    if not cfg.host.strip():
        return None
    user = (cfg.user or "").strip()
    password = (cfg.password or "").strip()
    from_addr = (cfg.from_addr or "").strip().lower()
    host = cfg.host.strip().lower()

    if not user:
        return "SMTP 用户名未填写。QQ/网易等邮箱请填写完整邮箱地址（如 name@qq.com）。"
    if "@" not in user:
        return (
            f"SMTP 用户名「{user}」不是邮箱地址。"
            "请到「平台配置 → 邮件 SMTP」改为完整发件邮箱（例如 name@qq.com），不要填登录用户名。"
        )
    if not password:
        return "SMTP 密码/授权码未设置。QQ 邮箱需在邮箱设置中生成授权码后填写到平台配置。"
    if from_addr in _PLACEHOLDER_FROM or not from_addr:
        return (
            "发件人 From 仍是默认占位地址。"
            "请到「平台配置 → 邮件 SMTP」将 From 改为与 SMTP 用户名相同的邮箱。"
        )
    if "@" in user and from_addr and from_addr != user.lower() and "qq.com" in host:
        return (
            f"QQ 邮箱要求发件人与登录邮箱一致：当前用户名为 {user}，From 为 {cfg.from_addr}。"
            "请将两者改为同一 QQ 邮箱后重试。"
        )
    return None


def smtp_public_view(cfg: SmtpRuntimeConfig) -> dict:
    warning = validate_smtp_ready(cfg) if cfg.configured else None
    return {
        "configured": cfg.configured,
        "host": cfg.host,
        "port": cfg.port,
        "user": cfg.user,
        "password_set": bool(cfg.password),
        "use_tls": cfg.use_tls,
        "use_ssl": cfg.use_ssl,
        "from_addr": cfg.from_addr,
        "dry_run": cfg.dry_run,
        "mode": "smtp" if cfg.configured else ("outbox" if cfg.dry_run else "disabled"),
        "warning": warning,
        "hint": (
            warning
            if warning
            else (
                "已配置 SMTP，发送将真实投递"
                if cfg.configured
                else (
                    "未配置 SMTP_HOST：发送将写入本地发件箱（开发演示）。"
                    "请在「平台配置」填写 SMTP，或设置环境变量 SMTP_HOST。"
                    if cfg.dry_run
                    else "未配置 SMTP，且未开启 dry-run，无法发送邮件"
                )
            )
        ),
    }
