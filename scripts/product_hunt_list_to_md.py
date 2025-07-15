import os
try:
    from dotenv import load_dotenv
    # 加载 .env 文件
    load_dotenv()
except ImportError:
    # 在 GitHub Actions 等环境中，环境变量已经设置好，不需要 dotenv
    print("dotenv 模块未安装，将直接使用环境变量")

import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import pytz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json

class Product:
    def __init__(self, id: str, name: str, tagline: str, description: str, votesCount: int, createdAt: str, featuredAt: str, website: str, url: str, media=None, **kwargs):
        self.name = name
        self.tagline = tagline
        self.description = description
        self.votes_count = votesCount
        self.created_at = self.convert_to_beijing_time(createdAt)
        self.featured = "是" if featuredAt else "否"
        self.website = website
        self.url = url
        self.og_image_url = self.get_image_url_from_media(media)
        self.keyword = self.generate_keywords()

    def get_image_url_from_media(self, media):
        """从API返回的media字段中获取图片URL"""
        try:
            if media and isinstance(media, list) and len(media) > 0:
                # 优先使用第一张图片
                image_url = media[0].get('url', '')
                if image_url:
                    print(f"成功从API获取图片URL: {self.name}")
                    return image_url
            
            # 如果API没有返回图片，尝试使用备用方法
            print(f"API未返回图片，尝试使用备用方法: {self.name}")
            backup_url = self.fetch_og_image_url()
            if backup_url:
                print(f"使用备用方法获取图片URL成功: {self.name}")
                return backup_url
            else:
                print(f"无法获取图片URL: {self.name}")
                
            return ""
        except Exception as e:
            print(f"获取图片URL时出错: {self.name}, 错误: {e}")
            return ""

    def fetch_og_image_url(self) -> str:
        """获取产品的Open Graph图片URL（备用方法）"""
        try:
            response = requests.get(self.url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # 查找og:image meta标签
                og_image = soup.find("meta", property="og:image")
                if og_image:
                    return og_image["content"]
                # 备用:查找twitter:image meta标签
                twitter_image = soup.find("meta", name="twitter:image") 
                if twitter_image:
                    return twitter_image["content"]
            return ""
        except Exception as e:
            print(f"获取OG图片URL时出错: {self.name}, 错误: {e}")
            return ""

    def generate_keywords(self) -> str:
        """生成产品的关键词，显示在一行，用逗号分隔"""
        try:
            # 使用简单的关键词提取方法
            words = set((self.name + ", " + self.tagline).replace("&", ",").replace("|", ",").replace("-", ",").split(","))
            return ", ".join([word.strip() for word in words if word.strip()])
        except Exception as e:
            print(f"关键词生成失败: {e}")
            return self.name  # 至少返回产品名称作为关键词

    def convert_to_beijing_time(self, utc_time_str: str) -> str:
        """将UTC时间转换为北京时间"""
        utc_time = datetime.strptime(utc_time_str, '%Y-%m-%dT%H:%M:%SZ')
        beijing_tz = pytz.timezone('Asia/Shanghai')
        beijing_time = utc_time.replace(tzinfo=pytz.utc).astimezone(beijing_tz)
        return beijing_time.strftime('%Y年%m月%d日 %p%I:%M (北京时间)')

    def to_dict(self) -> dict:
        """将产品数据转换为字典格式，用于发送到Webhook"""
        return {
            "name": self.name,
            "tagline": self.tagline,
            "description": self.description,
            "votes_count": self.votes_count,
            "created_at": self.created_at,
            "featured": self.featured,
            "website": self.website,
            "url": self.url,
            "og_image_url": self.og_image_url,
            "keyword": self.keyword
        }

def get_producthunt_token():
    """获取 Product Hunt 访问令牌"""
    # 直接返回硬编码的token
    return "pfL-2mZeM7TWpumhKEfPwiQTeRp-SWuOZxNLMcZ3k28"
    # 优先使用环境变量
    token = os.getenv('PRODUCTHUNT_DEVELOPER_TOKEN')
    if token:
        return token
    
    # 如果没有token，返回None，这样会使用模拟数据
    print("未找到Product Hunt token，将使用模拟数据")
    return None

def fetch_product_hunt_data():
    """从Product Hunt获取前一天的Top 30数据"""
    token = get_producthunt_token()
    if not token:
        raise Exception("No Product Hunt token available")
        
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    url = "https://api.producthunt.com/v2/api/graphql"
    
    # 添加更多请求头信息
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "DecohackBot/1.0 (https://decohack.com)",
        "Origin": "https://decohack.com",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Connection": "keep-alive"
    }

    # 设置重试策略
    retry_strategy = Retry(
        total=3,  # 最多重试3次
        backoff_factor=1,  # 重试间隔时间
        status_forcelist=[429, 500, 502, 503, 504]  # 需要重试的HTTP状态码
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)

    base_query = """
    {
      posts(order: VOTES, postedAfter: "%sT00:00:00Z", postedBefore: "%sT23:59:59Z", after: "%s") {
        nodes {
          id
          name
          tagline
          description
          votesCount
          createdAt
          featuredAt
          website
          url
          media {
            url
            type
            videoUrl
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
    """

    all_posts = []
    has_next_page = True
    cursor = ""

    while has_next_page and len(all_posts) < 30:
        query = base_query % (date_str, date_str, cursor)
        try:
            response = session.post(url, headers=headers, json={"query": query})
            response.raise_for_status()  # 抛出非200状态码的异常
            
            data = response.json()['data']['posts']
            posts = data['nodes']
            all_posts.extend(posts)

            has_next_page = data['pageInfo']['hasNextPage']
            cursor = data['pageInfo']['endCursor']
            
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            raise Exception(f"Failed to fetch data from Product Hunt: {e}")

    # 只保留前30个产品
    return [Product(**post) for post in sorted(all_posts, key=lambda x: x['votesCount'], reverse=True)[:30]]

def fetch_mock_data():
    """生成模拟数据用于测试"""
    print("使用模拟数据进行测试...")
    mock_products = [
        {
            "id": "1",
            "name": "Venice",
            "tagline": "Private & censorship-resistant AI | Unlock unlimited intelligence",
            "description": "Venice is a private, censorship-resistant AI platform powered by open-source models and decentralized infrastructure. The app combines the benefits of decentralized blockchain technology with the power of generative AI.",
            "votesCount": 566,
            "createdAt": "2025-03-07T16:01:00Z",
            "featuredAt": "2025-03-07T16:01:00Z",
            "website": "https://www.producthunt.com/r/4D6Z6F7I3SXTGN",
            "url": "https://www.producthunt.com/posts/venice-3",
            "media": [
                {
                    "url": "https://ph-files.imgix.net/97baee49-6dda-47f5-8a47-91d2c56e1976.jpeg",
                    "type": "image",
                    "videoUrl": None
                }
            ]
        },
        {
            "id": "2",
            "name": "Mistral OCR",
            "tagline": "Introducing the world's most powerful document understanding API",
            "description": "Introducing Mistral OCR—an advanced, lightweight optical character recognition model focused on speed, accuracy, and efficiency. Whether extracting text from images or digitizing documents, it delivers top-tier performance with ease.",
            "votesCount": 477,
            "createdAt": "2025-03-07T16:01:00Z",
            "featuredAt": "2025-03-07T16:01:00Z",
            "website": "https://www.producthunt.com/r/SPXNTAWQSVRLGH",
            "url": "https://www.producthunt.com/posts/mistral-ocr",
            "media": [
                {
                    "url": "https://ph-files.imgix.net/4224517b-29e4-4944-98c9-2eee59374870.png",
                    "type": "image",
                    "videoUrl": None
                }
            ]
        },
        {
            "id": "3",
            "name": "AI Code Reviewer",
            "tagline": "Automated code review powered by AI",
            "description": "An intelligent code review tool that uses AI to analyze your code, suggest improvements, and catch potential bugs before they reach production.",
            "votesCount": 324,
            "createdAt": "2025-03-07T14:30:00Z",
            "featuredAt": None,
            "website": "https://example.com/ai-code-reviewer",
            "url": "https://www.producthunt.com/posts/ai-code-reviewer",
            "media": []
        }
    ]
    return [Product(**product) for product in mock_products]

def send_to_webhook(products):
    """将产品数据发送到飞书Webhook"""
    # 更新为新的webhook URL
    webhook_url = os.getenv('FEISHU_WEBHOOK_URL', 'https://larkcommunity.feishu.cn/base/workflow/webhook/event/O7fjaz3CTw5lHOh5g0ccP70EnKf')
    
    # 获取今天的日期
    today = datetime.now(timezone.utc)
    date_today = today.strftime('%Y-%m-%d')
    
    # 构建要发送的JSON数据 - 包含更丰富的产品信息
    products_data = []
    for i, product in enumerate(products[:10]):  # 只发送前10个产品
        product_info = {
            "排名": i + 1,
            "产品名称": product.name,
            "标语": product.tagline,
            "详细描述": product.description,
            "产品图片链接": product.og_image_url,
            "票数": product.votes_count,
            "创建时间": product.created_at,
            "是否精选": product.featured,
            "官方网站": product.website,
            "Product Hunt链接": product.url,
            "关键词": product.keyword,
            "媒体类型": "图片" if product.og_image_url else "无图片"
        }
        products_data.append(product_info)
    
    # 添加统计信息
    total_votes = sum(product.votes_count for product in products[:10])
    avg_votes = total_votes // len(products[:10]) if products else 0
    
    data = {
        "日期": date_today,
        "数据来源": "Product Hunt API",
        "产品总数": len(products_data),
        "总票数": total_votes,
        "平均票数": avg_votes,
        "最高票数": products[0].votes_count if products else 0,
        "最低票数": products[min(9, len(products)-1)].votes_count if products else 0,
        "产品列表": products_data
    }
    
    print(f"准备发送数据到Webhook: {webhook_url}")
    print(f"发送的JSON数据预览:")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:1500] + "..." if len(json.dumps(data, ensure_ascii=False)) > 1500 else json.dumps(data, ensure_ascii=False, indent=2))
    
    # 发送JSON数据到webhook
    try:
        response = requests.post(webhook_url, json=data, timeout=10)
        response.raise_for_status()
        print(f"成功发送数据到Webhook: {response.status_code}")
        return True
    except Exception as e:
        print(f"发送到Webhook失败: {e}")
        return False

def main():
    print("开始运行Product Hunt数据获取程序...")
    
    # 获取昨天的日期并格式化
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    print(f"获取日期: {date_str}")

    try:
        # 尝试获取Product Hunt数据
        print("尝试从Product Hunt API获取数据...")
        products = fetch_product_hunt_data()
        print(f"成功获取到 {len(products)} 个产品")
    except Exception as e:
        print(f"获取Product Hunt数据失败: {e}")
        print("使用模拟数据继续...")
        products = fetch_mock_data()
        print(f"使用模拟数据，共 {len(products)} 个产品")

    # 显示产品信息
    print("\n=== 产品列表 ===")
    for i, product in enumerate(products[:5], 1):  # 只显示前5个
        print(f"{i}. {product.name}")
        print(f"   标语: {product.tagline}")
        print(f"   票数: {product.votes_count}")
        print(f"   时间: {product.created_at}")
        print()

    # 发送数据到Webhook
    print("发送数据到Webhook...")
    success = send_to_webhook(products)
    
    if success:
        print("程序执行完成！")
    else:
        print("程序执行完成，但Webhook发送失败")

if __name__ == "__main__":
    main()
