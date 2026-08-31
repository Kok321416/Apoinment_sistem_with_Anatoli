from aiogram import Router

from bot.handlers import callbacks, commands
from bot.handlers.ops_alert_bind import OpsAlertBindMiddleware


def setup_routers() -> Router:
    root = Router(name="root")
    root.message.middleware(OpsAlertBindMiddleware())
    root.include_router(commands.router)
    root.include_router(callbacks.router)
    return root
