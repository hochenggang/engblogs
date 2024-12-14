import os
import requests
import xmltodict

# 加载 OPML 文件
def load_opml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return xmltodict.parse(file.read())

# 保存更新后的 OPML 文件
def save_opml(opml_data, file_path):
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(xmltodict.unparse(opml_data, pretty=True))

# 提取所有 xmlUrl 的值
def extract_urls(opml_data):
    outlines = opml_data['opml']['body']['outline']
    return [item['@xmlUrl'] for item in outlines]

# 删除无效的 URL
def remove_bad_urls(opml_data, bad_urls):
    outlines = opml_data['opml']['body']['outline']
    opml_data['opml']['body']['outline'] = [item for item in outlines if item['@xmlUrl'] not in bad_urls]

def main():
    file_path = 'engblogs.opml'
    opml_data = load_opml(file_path)
    
    # 提取所有订阅 URL
    all_urls = extract_urls(opml_data)

    # 从环境变量中获取 Token
    auth_token = os.getenv('AUTH_TOKEN')
    if not auth_token:
        raise ValueError("Authorization token not found in environment variables.")
    
    # 设置请求头部
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }
    
    # 调用 API 检查 URL 有效性
    response = requests.post(
        'https://v2.weekly.imhcg.cn/urls/status/bad', 
        json={'urls': all_urls},
        headers=headers
    )
    response.raise_for_status()
    bad_urls = response.json()
    
    # 更新 OPML 数据
    if bad_urls:
        remove_bad_urls(opml_data, bad_urls)
        save_opml(opml_data, file_path)

if __name__ == '__main__':
    main()
