import time
import re
import base64
import hashlib
import rsa
import requests
from environs import Env

env = Env()
env.read_env()


def int_to_base36_char(value):
    base36_chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    return base36_chars[value]


def base64_to_hex(b64_string):
    B64MAP = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    hex_string = ""
    carry = 0
    buffer = 0
    for char in b64_string:
        if char != "=":
            value = B64MAP.index(char)
            if carry == 0:
                carry = 1
                hex_string += int_to_base36_char(value >> 2)
                buffer = 3 & value
            elif carry == 1:
                carry = 2
                hex_string += int_to_base36_char(buffer << 2 | value >> 4)
                buffer = 15 & value
            elif carry == 2:
                carry = 3
                hex_string += int_to_base36_char(buffer)
                hex_string += int_to_base36_char(value >> 2)
                buffer = 3 & value
            else:
                carry = 0
                hex_string += int_to_base36_char(buffer << 2 | value >> 4)
                hex_string += int_to_base36_char(15 & value)
    if carry == 1:
        hex_string += int_to_base36_char(buffer << 2)
    return hex_string


def rsa_encrypt(public_key, message):
    rsa_key = f"-----BEGIN PUBLIC KEY-----\n{public_key}\n-----END PUBLIC KEY-----"
    pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(rsa_key.encode())
    result = base64_to_hex((base64.b64encode(rsa.encrypt(f'{message}'.encode(), pubkey))).decode())
    return result


def calculate_md5_sign(params):
    return hashlib.md5('&'.join(sorted(params.split('&'))).encode('utf-8')).hexdigest()


def login(username, password):
    try:
        session = requests.Session()
        urlToken = ("https://m.cloud.189.cn/udb/udb_login.jsp?pageId=1&pageKey=default&clientType=wap&redirectURL"
                    "=https://m.cloud.189.cn/zhuanti/2021/shakeLottery/index.html")
        response = session.get(urlToken)

        url_match = re.search(r"https?://[^\s'\"]+", response.text)
        if not url_match:
            raise Exception("登录URL未找到")
        redirect_url = url_match.group()

        response = session.get(redirect_url)
        href_match = re.search(r'<a id="j-tab-login-link"[^>]*href="([^\"]+)"', response.text)
        if not href_match:
            raise Exception("登录链接未找到")
        login_href = href_match.group(1)

        response = session.get(login_href)
        captcha_token = re.findall(r"captchaToken' value='(.+?)'", response.text)[0]
        lt = re.findall(r'lt = "(.+?)"', response.text)[0]
        return_url = re.findall(r"returnUrl= '(.+?)'", response.text)[0]
        param_id = re.findall(r'paramId = "(.+?)"', response.text)[0]
        rsa_key = re.findall(r'j_rsaKey" value="(\S+)"', response.text, re.M)[0]
        session.headers.update({"lt": lt})

        encrypted_username = rsa_encrypt(rsa_key, username)
        encrypted_password = rsa_encrypt(rsa_key, password)
        url = "https://open.e.189.cn/api/logbox/oauth2/loginSubmit.do"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:74.0) Gecko/20100101 Firefox/76.0',
            'Referer': 'https://open.e.189.cn/',
        }
        login_payload = {
            "appKey": "cloud",
            "accountType": '01',
            "userName": f"{{RSA}}{encrypted_username}",
            "password": f"{{RSA}}{encrypted_password}",
            "validateCode": "",
            "captchaToken": captcha_token,
            "returnUrl": return_url,
            "mailSuffix": "@189.cn",
            "paramId": param_id
        }
        login_response = session.post(url, data=login_payload, headers=headers, timeout=5)
        login_info = login_response.json()
        if login_info['result'] == 0:
            print(login_info['msg'])
        else:
            raise Exception(f"{login_info['msg']}")
        redirect_url = login_info['toUrl']
        session.get(redirect_url)
        return session
    except Exception as e:
        send_msg(f"账号 {username}\n登录失败: {str(e)}")
        return None


def check_in(username, password):
    max_retries = 3
    session = None
    while max_retries:
        session = login(username, password)
        if session:
            break
        max_retries -= 1

    if not session:
        print(f"账号 {username} 登录失败")
        return

    rand_timestamp = str(round(time.time() * 1000))
    sign_in_url = (
        f'https://api.cloud.189.cn/mkt/userSign.action?rand={rand_timestamp}&clientType=TELEANDROID&version=8.6.3'
        f'&model=SM-G930K')

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 5.1.1; SM-G930K Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, '
                      'like Gecko) Version/4.0 Chrome/74.0.3729.136 Mobile Safari/537.36 Ecloud/8.6.3 Android/22 '
                      'clientId/355325117317828 clientModel/SM-G930K imsi/460071114317824 clientChannelId/qq '
                      'proVersion/1.0.6',
        "Referer": "https://m.cloud.189.cn/zhuanti/2016/sign/index.jsp?albumBackupOpened=1",
        "Host": "m.cloud.189.cn",
        "Accept-Encoding": "gzip, deflate",
    }
    response = session.get(sign_in_url, headers=headers)
    netdisk_bonus = response.json()['netdiskBonus']

    content = f"账号 {username}\n签到获得 {netdisk_bonus}M 空间"

    send_msg(content)


def send_msg(content):
    url = "https://api.xbxin.com/msg/admin/corp"
    token = env.str("TOKEN")

    headers = {
        'Authorization': f'Bearer {token}',
    }

    data = {
        "title": "天翼云盘",
        "desc": "签到",
        "content": content
    }

    requests.post(url, json=data, headers=headers)


def main():
    users = env.json("TY_CLOUD")
    for user in users:
        username = user['username']
        password = user['password']
        check_in(username, password)


if __name__ == "__main__":
    main()
