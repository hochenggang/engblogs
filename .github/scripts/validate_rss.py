import os
import requests
import xmltodict

def load_opml(file_path):
    """加载 OPML 文件"""
    with open(file_path, 'r', encoding='utf-8') as file:
        return xmltodict.parse(file.read())

def save_opml(opml_data, file_path):
    """保存更新后的 OPML 文件"""
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(xmltodict.unparse(opml_data, pretty=True))

def extract_urls(opml_data):
    """提取所有 xmlUrl 的值"""
    outlines = opml_data['opml']['body']['outline']
    return [item['@xmlUrl'] for item in outlines]

def remove_bad_urls(opml_data, bad_urls):
    """删除无效的 URL"""
    outlines = opml_data['opml']['body']['outline']
    opml_data['opml']['body']['outline'] = [item for item in outlines if item['@xmlUrl'] not in bad_urls]

def render_status_table(status_data, output_file):
    """将状态数据渲染为 Markdown 表格"""
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write("| URL | Location | Success | Elapsed Time (s) | Insert Time |\n")
        file.write("| --- | --- | --- | --- | --- |\n")

        for url, locations in status_data.items():
            for location, details in locations.items():
                file.write(f"| {url} | {location} | {details['success']} | {details['elapsed_time']:.3f} | {details['insert_time']} |\n")

def process_file(file_path, auth_token):
    """处理单个 OPML 文件"""
    opml_data = load_opml(file_path)

    # 提取所有订阅 URL
    all_urls = extract_urls(opml_data)

    # 设置请求头部
    headers = {
        'Authorization': f'Bearer {auth_token}',
        'Content-Type': 'application/json'
    }

    # 调用 API 检查 URL 无效性
    response_bad = requests.post(
        'https://v2.weekly.imhcg.cn/urls/status/bad', 
        json={'urls': all_urls},
        headers=headers
    )
    response_bad.raise_for_status()
    bad_urls = response_bad.json()

    # 更新 OPML 数据
    if bad_urls:
        remove_bad_urls(opml_data, bad_urls)
        save_opml(opml_data, file_path)

    # 提取更新后的 URL 列表
    updated_urls = extract_urls(opml_data)

    # 调用 API 获取 URL 状态
    response_status = requests.post(
        'https://v2.weekly.imhcg.cn/urls/status/', 
        json={'urls': updated_urls},
        headers=headers
    )
    response_status.raise_for_status()
    urls_status = response_status.json()

    # 保存状态表为 Markdown 文件
    status_output_file = file_path.replace('.opml', '_status.md')
    render_status_table(urls_status, status_output_file)

    return len(bad_urls)

def main():
    files_to_process = ['engblogs.opml', 'cngblogs.opml']  # 需要处理的文件
    auth_token = os.getenv('AUTH_TOKEN')

    if not auth_token:
        raise ValueError("Authorization token not found in environment variables.")

    total_removed = 0

    for file_path in files_to_process:
        if os.path.exists(file_path):
            num_removed = process_file(file_path, auth_token)
            print(f"{file_path}: 移除 {num_removed} 项无法访问的订阅")
            total_removed += num_removed
        else:
            print(f"文件 {file_path} 不存在，跳过。")

    print(f"总计移除 {total_removed} 项无法访问的订阅。")

if __name__ == '__main__':
    main()
