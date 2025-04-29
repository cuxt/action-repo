import requests
from environs import Env


def query(account):
    url = f'{account["url"]}/v1/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {account["key"]}',
    }
    data = {
        'model': 'gpt-4o-mini',
        'messages': [
            {
                'role': 'user',
                'content': '请你翻译这个句子：Hello, how are you?'
            }
        ],
        'temperature': 0.7,
        'top_p': 1,
        'frequency_penalty': 0,
        'presence_penalty': 0,
        'stream': False
    }

    requests.post(url, headers=headers, json=data)


def main():
    env = Env()
    env.read_env()
    accounts = env.json('ONE_API')
    for account in accounts:
        query(account)


if __name__ == '__main__':
    main()
