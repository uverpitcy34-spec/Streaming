import os
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# ── 【設計図】ジャンルごとに明確に分けて管理 ──
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
    "5. 経営戦略・コンサル": [
        "https://www.dhbr.net/rss",
        "https://toyokeizai.net/list/feed/rss",
        "https://diamond.jp/rss/articles",
        "https://business.nikkei.com/rss/bn/nb.rdf"
    ]
}

def fetch_all_genres():
    structured_data = ""
    seen_links = set()  # 重複記事をURL単位で完全に排除するセット

    # ジャンルごとにループを回してデータを綺麗にカプセル化する
    for genre_name, urls in GENRE_CHANNELS.items():
        structured_data += f"\n\n【ジャンル：{genre_name}】\n"
        
        genre_articles_count = 0
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:3]:
                    link = entry.link
                    
                    # 別のRSSで既に取得済みの同一URL（重複）があれば完全にスキップ
                    if link in seen_links:
                        continue
                    
                    seen_links.add(link)
                    title = entry.title
                    summary = entry.get("summary", "")[:200]
                    
                    structured_data += f"- タイトル: {title}\n  URL: {link}\n  概要: {summary}\n"
                    genre_articles_count += 1
            except Exception as e:
                print(f"Warning: Failed to parse {url}. Error: {e}")
                continue
                
        if genre_articles_count == 0:
            structured_data += "(このジャンルの本日の新規投稿はありません)\n"
            
    return structured_data

def generate_summary(structured_articles_text):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
        
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    あなたはプロフェッショナルなコンサルタントの右腕となる、極めて優秀なシニアリサーチャーです。
    提供された【ジャンル別・記事データ】の構造をそのまま維持し、日本の読者向けに毎朝のニュース配信テキストを作成してください。

    【絶対厳守ルール】
    1. 提供されたデータに実在しないニュース、存在しないURLは1文字たりとも創作してはいけません（ハルシネーションの徹底排除）。
    2. 各記事のURLは、データにあるものをそのまま完全に出力してください。
    3. 海外ソース（英語のタイトルや本文）は、必ず高度なビジネス日本語に翻訳した上で要約を行ってください。
    4. インプットの【ジャンル】の枠組み（1〜5）を絶対に崩さず、各ジャンルの中からコンサル実務において「最もインサイトがある重要なトピック」を厳選して出力してください。各ジャンルの見出し（■）は必ず維持してください。

    【出力フォーマット】
    ■ 1. AI最新動向（国内）
      - [記事タイトル]
        要約文（3行程度で具体的かつ実務での価値を記述）
        🔗 [URL]

    ■ 2. AI最新動向（海外・英語）
      - [記事タイトル（日本語訳）]
        要約文（3行程度）
        🔗 [URL]

    (以下、ジャンル5まで同様に仕分けて出力)

    【提供されたジャンル別・記事データ】
    {structured_articles_text}
    """
    
    response = model.generate_content(prompt)
    return response.text

def send_to_line(text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        raise ValueError("LINEの認証情報が設定されていません。")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": text}]
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        print("LINEへの配信に成功しました！")
    else:
        print(f"エラーが発生しました: {response.text}")

if __name__ == "__main__":
    print("5つのジャンル別にRSSソースから重複を排除して取得中...")
    processed_data = fetch_all_genres()
    
    print("Geminiでジャンル構造を維持したまま、翻訳・要約を生成中...")
    summary_text = generate_summary(processed_data)
    
    print("スマホのLINEへ送信中...")
    send_to_line(summary_text[:4900])
