import os
import json
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta

# .envファイルから環境変数（鍵）を読み込む
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# ── 【最新版・6大ジャンル設計図】 ──
GENRE_CHANNELS = {
    "1. AI最新動向（国内）": [
        "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
        "https://www.publickey1.jp/atom.xml",
        "https://ascii.jp/rss/rss_ai.xml"
    ],
    "2. AI最新動向（海外・英語）": [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://venturebeat.com/category/ai/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"
    ],
    "3. AI実務Tips・Pythonコーディング": [
        "https://qiita.com/tags/ai/feed",
        "https://qiita.com/tags/langchain/feed",
        "https://qiita.com/tags/python/feed",
        "https://zenn.dev/topics/llm/feed",
        "https://zenn.dev/topics/ai/feed",
        "https://zenn.dev/topics/python/feed"
    ],
    "4. 企業DX・IT導入事例": [
        "https://enterprisezine.jp/rss/new/",
        "https://japan.zdnet.com/rss/",
        "https://xtech.nikkei.com/rss/index.rdf",
        "https://rss.itmedia.co.jp/rss/2.0/business.xml"
    ],
    "5. 経営・ビジネス情報（日経等）": [
        "https://business.nikkei.com/rss/bn/nb.rdf",           # 日経ビジネス
        "https://toyokeizai.net/list/feed/rss",                # 東洋経済オンライン
        "https://diamond.jp/rss/articles",                     # ダイヤモンドオンライン
        "https://www.dhbr.net/rss"                             # Harvard Business Review日本版
    ],
    "6. コンサルティング業界動向": [
        "https://www.consulnews.jp/feed/"                      # コンサル業界ニュース（専門誌）
    ]
}

def fetch_all_genres():
    structured_data = ""
    seen_links = set()
    
    # 直近72時間（3日間）の記事をプール
    now = datetime.now()
    time_threshold = now - timedelta(hours=72)

    for genre_name, urls in GENRE_CHANNELS.items():
        structured_data += f"\n\n【{genre_name}】\n"
        genre_articles_count = 0
        
        for url in urls:
            try:
                feed = feedparser.parse(url)
                
                # 「5. 経営・ビジネス情報」は大量にプールするため、1メディアあたり15本まで貪欲に取得
                max_fetch = 15 if "5." in genre_name else 5
                
                for entry in feed.entries[:max_fetch]:
                    link = entry.link
                    
                    if link in seen_links:
                        continue
                    
                    # 日付チェック
                    published_tok = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published_tok:
                        published_dt = datetime(*published_tok[:6])
                        if published_dt < time_threshold:
                            continue
                    
                    seen_links.add(link)
                    title = entry.title
                    summary = entry.get("summary", "")[:250]
                    
                    structured_data += f"- タイトル: {title}\n  URL: {link}\n  概要: {summary}\n"
                    genre_articles_count += 1
            except Exception as e:
                print(f"Warning: Failed to parse {url}. Error: {e}")
                continue
                
        if genre_articles_count == 0:
            structured_data += "(このジャンルの直近3日間の新規投稿はありません)\n"
            
    return structured_data

def generate_summary(structured_articles_text):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
        
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    あなたはプロフェッショナルなコンサルタントの右腕となる、非常に優秀なシニアリサーチャーです。
    提供された【ジャンル別・記事データ】から重要トピックを厳選し、指定の【配信本数ルール】を厳格に守って、日本の読者向けにニュースデータを抽出・翻訳・要約してください。

    【絶対厳守ルール】
    1. 提供されたデータに実在しないニュース、存在しないURLは絶対に創作しないでください（ハルシネーションの徹底排除）。
    2. 各記事のURLは、データにあるものをそのまま完全に出力してください。
