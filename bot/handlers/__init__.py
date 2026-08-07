from aiogram import Router

from bot.handlers import callbacks, commands


def setup_routers() -> Router:
    root = Router(name="root")
    root.include_router(commands.router)
    root.include_router(callbacks.router)
    return root
