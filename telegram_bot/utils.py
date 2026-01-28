import hashlib
import hmac
from urllib.parse import parse_qsl


def validate_telegram_webapp_init_data(init_data: str, bot_token: str) -> dict:
    """
    Валидирует Telegram WebApp initData.
    Возвращает распарсенные поля, если подпись корректна, иначе поднимает ValueError.

    Алгоритм: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    if not init_data:
        raise ValueError("init_data пустой")
    if not bot_token:
        raise ValueError("bot_token пустой")

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise ValueError("hash отсутствует в init_data")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if calculated_hash != received_hash:
        raise ValueError("Неверная подпись init_data")

    return data


