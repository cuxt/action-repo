import requests
import hashlib
import time
from environs import Env

env = Env()
env.read_env()


def keep_alive(ctyun, user_data, retries=3, delay=10):
    # 设置API的URL和路径
    url = "https://desk.ctyun.cn:8810/api/"
    computer_connect = "desktop/client/connect"

    # 设置连接云电脑时需要的设备信息
    device_info = {
        "objId": ctyun["objId"],
        "objType": 0,
        "osType": 15,
        "deviceId": 60,
        "deviceCode": ctyun["deviceCode"],
        "deviceName": "Edge浏览器",
        "sysVersion": "Windows NT 10.0; Win64; x64",
        "appVersion": "1.36.1",
        "hostName": "Edge浏览器",
        "vdCommand": "",
        "ipAddress": "",
        "macAddress": "",
        "hardwareFeatureCode": ctyun["deviceCode"]
    }

    # 配置请求头中需要的一些参数
    app_model_value = "2"
    device_code_value = ctyun["deviceCode"]
    device_type_value = "60"
    request_id_value = "1718366052351"
    tenant_id_value = "15"
    timestamp_value = str(int(time.time() * 1000))
    userid_value = str(user_data["userId"])
    version_value = "201360101"
    secret_key_value = user_data["secretKey"]

    # 创建签名字符串
    signature_str = device_type_value + request_id_value + tenant_id_value + timestamp_value + userid_value + version_value + secret_key_value

    # 使用MD5算法创建签名
    hash_obj = hashlib.md5()
    hash_obj.update(signature_str.encode('utf-8'))
    digest_hex = hash_obj.hexdigest().upper()

    # 准备请求头
    headers = {
        'ctg-appmodel': app_model_value,
        'ctg-devicecode': device_code_value,
        'ctg-devicetype': device_type_value,
        'ctg-requestid': request_id_value,
        'ctg-signaturestr': digest_hex,
        'ctg-tenantid': tenant_id_value,
        'ctg-timestamp': timestamp_value,
        'ctg-userid': userid_value,
        'ctg-version': version_value,
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    }

    # 发起POST请求连接云电脑
    for attempt in range(retries):
        try:
            response = requests.post(url + computer_connect, data=device_info, headers=headers, timeout=30)
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
    url = env.str('PUSH_URL')

    data = {
        "title": "天翼云电脑",
        "content": content
    }

    requests.post(url, json=data)

def sha256(password):
    hasher = hashlib.sha256()
    hasher.update(password.encode('utf-8'))
    return hasher.hexdigest()


def login(ctyun):
    headers = {
        'ctg-appmodel': '2',
        'ctg-devicecode': ctyun["deviceCode"],
        'ctg-devicetype': '60',
        'ctg-requestid': '1718366047928',
        'ctg-timestamp': str(int(time.time() * 1000)),
        'ctg-version': '201360101',
        'dnt': '1',
        'origin': 'https://pc.ctyun.cn',
        'priority': 'u=1, i',
        'referer': 'https://pc.ctyun.cn/',
        'sec-ch-ua': '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'sec-gpc': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
    }

    account = ctyun["account"]
    password = sha256(ctyun["password"])

    data = {
        'userAccount': account,
        'password': password,
        'sha256Password': password,
        'deviceCode': ctyun["deviceCode"],
        'deviceName': 'Edge浏览器',
        'deviceType': '60',
        'deviceModel': 'Windows NT 10.0; Win64; x64',
        'appVersion': '1.36.1',
        'sysVersion': 'Windows NT 10.0; Win64; x64',
        'clientVersion': '201360101',
    }

    response = requests.post('https://desk.ctyun.cn:8810/api/auth/client/login', headers=headers, data=data)

    data = response.json()
    user_data = {}
    if data["code"] == 0:
        user_data["userId"] = data["data"]["userId"]
        user_data["secretKey"] = data["data"]["secretKey"]
        return user_data
    else:
        send_msg(f"登录失败：{data}")
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
                send_msg(f"保活失败：{data}")
        except Exception as e:
            send_msg(f"保活失败：{e}")


if __name__ == '__main__':
    main()
