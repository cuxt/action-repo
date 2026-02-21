import base64
import logging
import re
import time
from dataclasses import dataclass
from typing import cast

import requests
import rsa
from environs import Env

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

LOGIN_PAGE_URL = (
    "https://m.cloud.189.cn/udb/udb_login.jsp?pageId=1&pageKey=default"
    "&clientType=wap&redirectURL=https://m.cloud.189.cn/zhuanti/2021/shakeLottery/index.html"
)
LOGIN_SUBMIT_URL = "https://open.e.189.cn/api/logbox/oauth2/loginSubmit.do"
SIGN_IN_URL = "https://api.cloud.189.cn/mkt/userSign.action"

B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
HEX_CHARS = "0123456789abcdef"

MAX_LOGIN_RETRIES = 3


@dataclass
class Account:
    username: str
    password: str


def _b64_to_hex(b64_str: str) -> str:
    result: list[str] = []
    carry = 0
    buffer = 0

    for ch in b64_str:
        if ch == "=":
            continue
        value = B64_ALPHABET.index(ch)
        if carry == 0:
            carry = 1
            result.append(HEX_CHARS[value >> 2])
            buffer = value & 0x3
        elif carry == 1:
            carry = 2
            result.append(HEX_CHARS[(buffer << 2) | (value >> 4)])
            buffer = value & 0xF
        elif carry == 2:
            carry = 3
            result.append(HEX_CHARS[buffer])
            result.append(HEX_CHARS[value >> 2])
            buffer = value & 0x3
        else:
            carry = 0
            result.append(HEX_CHARS[(buffer << 2) | (value >> 4)])
            result.append(HEX_CHARS[value & 0xF])

    if carry == 1:
        result.append(HEX_CHARS[buffer << 2])

    return "".join(result)


def _rsa_encrypt(public_key_b64: str, plaintext: str) -> str:
    pem = f"-----BEGIN PUBLIC KEY-----\n{public_key_b64}\n-----END PUBLIC KEY-----"
    pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(pem.encode())
    encrypted = rsa.encrypt(plaintext.encode(), pubkey)
    return _b64_to_hex(base64.b64encode(encrypted).decode())


def _extract_login_params(html: str) -> dict[str, str]:
    patterns = {
        "captcha_token": r"captchaToken' value='(.+?)'",
        "lt": r'lt = "(.+?)"',
        "return_url": r"returnUrl= '(.+?)'",
        "param_id": r'paramId = "(.+?)"',
        "rsa_key": r'j_rsaKey" value="(\S+)"',
    }
    params: dict[str, str] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, html)
        if not match:
            raise ValueError(f"登录页面中未找到参数: {name}")
        params[name] = match.group(1)
    return params


def _send_notification(push_url: str, content: str) -> None:
    try:
        requests.post(push_url, json={"title": "天翼云盘签到", "content": content}, timeout=60)
    except requests.RequestException as e:
        logger.warning("通知发送失败: %s", e)


def _login(session: requests.Session, account: Account) -> bool:
    # 获取登录入口页，跟随重定向拿到统一认证页面
    resp = session.get(LOGIN_PAGE_URL, timeout=60)
    url_match = re.search(r"https?://[^\s'\"]+", resp.text)
    if not url_match:
        raise ValueError("登录入口页中未找到重定向URL")

    resp = session.get(url_match.group(), timeout=60)
    href_match = re.search(r'<a id="j-tab-login-link"[^>]*href="([^"]+)"', resp.text)
    if not href_match:
        raise ValueError("认证页面中未找到登录链接")

    resp = session.get(href_match.group(1), timeout=60)
    params = _extract_login_params(resp.text)

    session.headers.update({"lt": params["lt"]})

    payload = {
        "appKey": "cloud",
        "accountType": "01",
        "userName": f"{{RSA}}{_rsa_encrypt(params['rsa_key'], account.username)}",
        "password": f"{{RSA}}{_rsa_encrypt(params['rsa_key'], account.password)}",
        "validateCode": "",
        "captchaToken": params["captcha_token"],
        "returnUrl": params["return_url"],
        "mailSuffix": "@189.cn",
        "paramId": params["param_id"],
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) Gecko/20100101 Firefox/76.0",
        "Referer": "https://open.e.189.cn/",
    }

    resp = session.post(LOGIN_SUBMIT_URL, data=payload, headers=headers, timeout=60)
    result = resp.json()

    if result["result"] != 0:
        raise RuntimeError(f"登录接口返回错误: {result['msg']}")

    logger.info("登录成功: %s", result["msg"])
    session.get(result["toUrl"], timeout=60)
    return True


def _sign_in(session: requests.Session) -> int:
    params = {
        "rand": str(round(time.time() * 1000)),
        "clientType": "TELEANDROID",
        "version": "8.6.3",
        "model": "SM-G930K",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 5.1.1; SM-G930K Build/NRD90M; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/74.0.3729.136 "
            "Mobile Safari/537.36 Ecloud/8.6.3 Android/22 clientId/355325117317828 "
            "clientModel/SM-G930K imsi/460071114317824 clientChannelId/qq proVersion/1.0.6"
        ),
        "Referer": "https://m.cloud.189.cn/zhuanti/2016/sign/index.jsp?albumBackupOpened=1",
        "Host": "m.cloud.189.cn",
        "Accept-Encoding": "gzip, deflate",
    }

    resp = session.get(SIGN_IN_URL, params=params, headers=headers, timeout=60)
    data = resp.json()
    return int(data["netdiskBonus"])


def check_in(account: Account, push_url: str) -> None:
    session = requests.Session()

    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        try:
            _login(session, account)
            break
        except Exception as e:
            logger.warning("账号 %s 第 %d 次登录失败: %s", account.username, attempt, e)
            if attempt == MAX_LOGIN_RETRIES:
                _send_notification(push_url, f"账号 {account.username}\n登录失败: {e}")
                return

    try:
        bonus = _sign_in(session)
        msg = f"账号 {account.username} 签到获得 {bonus}M 空间"
        logger.info(msg)
        _send_notification(push_url, msg)
    except Exception as e:
        logger.error("账号 %s 签到失败: %s", account.username, e)
        _send_notification(push_url, f"账号 {account.username}\n签到失败: {e}")


def main() -> None:
    env = Env()
    env.read_env()

    push_url: str = env.str("PUSH_URL")
    users = cast(list[dict[str, str]], env.json("TY_CLOUD"))

    for user in users:
        account = Account(username=user["username"], password=user["password"])
        check_in(account, push_url)


if __name__ == "__main__":
    main()
