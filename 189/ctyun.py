import random
import requests
import hashlib
import time
from environs import Env

env = Env()
env.read_env()

device_type = "60"
base_url = "https://desk.ctyun.cn:8810/api"
request_id = str(int(time.time() * 1000) + random.randint(-100, 100))


def keep_alive(ctyun, user_data, retries=3, delay=10):
    url = f"{base_url}/desktop/client/connect"

    data = {
        "objId": ctyun["objId"],
        "objType": 0,
    }

    tenant_id_value = "15"
    timestamp_value = str(int(time.time() * 1000))
    userid_value = str(user_data["userId"])
    version_value = "1020700001"
    secret_key_value = user_data["secretKey"]

    # 创建签名字符串
    signature_str = (
        device_type
        + request_id
        + tenant_id_value
        + timestamp_value
        + userid_value
        + version_value
        + secret_key_value
    )

    # 使用MD5算法创建签名
    hash_obj = hashlib.md5()
    hash_obj.update(signature_str.encode("utf-8"))
    digest_hex = hash_obj.hexdigest().upper()

    # 请求头
    headers = {
        "ctg-devicetype": device_type,
        "ctg-requestid": request_id,
        "ctg-signaturestr": digest_hex,
        "ctg-tenantid": tenant_id_value,
        "ctg-timestamp": timestamp_value,
        "ctg-userid": userid_value,
        "ctg-version": version_value,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    }

    # 发起POST请求连接云电脑
    for attempt in range(retries):
        try:
            response = requests.post(url, data=data, headers=headers, timeout=30)
            response.raise_for_status()
            # print(response.json())
            return response.json()
        except requests.exceptions.ConnectTimeout:
            if attempt < retries - 1:
                time.sleep(delay)
                continue
            else:
                raise "连接超时"
    return None


def send_msg(content):
    url = env.str("PUSH_URL")

    data = {"title": "天翼云电脑", "content": content}

    requests.post(url, json=data)


def sha256(password):
    hasher = hashlib.sha256()
    hasher.update(password.encode("utf-8"))
    return hasher.hexdigest()


def login(ctyun):
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    }

    account = ctyun["account"]
    password = sha256(ctyun["password"])

    data = {
        "userAccount": account,
        "password": password,
        "sha256Password": password,
        "deviceCode": ctyun["deviceCode"],
        "deviceName": "Chrome浏览器",
        "deviceType": device_type,
        "clientVersion": "2.7.0",
    }

    response = requests.post(
        f"{base_url}/auth/client/login", headers=headers, data=data
    )

    data = response.json()
    if data["code"] == 0:
        return data["data"]
    else:
        send_msg(f"登录失败：{data['msg']}")
        return None


def main():
    ctyuns = env.json("CTYUN")
    for ctyun in ctyuns:
        try:
            user_data = login(ctyun)
            if user_data is None:
                continue
            data = keep_alive(ctyun, user_data)
            # print(data)
            code = data["code"]
            if code != 0:
                send_msg(f"保活失败：{data['msg']}")
        except Exception as e:
            send_msg(f"保活失败：{e}")


if __name__ == "__main__":
    main()
