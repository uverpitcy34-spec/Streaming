import os
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

# ==========================================
# 1. 環境変数からの安全な読み込み
# ==========================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# 信頼できるRSSフィードのリスト
RSS_URLS = [
    "https://techlife.cookpad.com/feed",
    "https://rss.itmedia.co.jp/rss/2.0/itmediaall.xml",
    "https://b.hatena.ne.jp/hotentry/it.rss"
]

def fetch_latest_articles():
    articles = []
    for url in RSS_URLS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "summary": entry.get("summary", "")[:200]
            })
    return articles

def generate_summary(articles):
    # APIキーが正しく読み込めているかチェック
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。.envファイルを確認してください。")
        
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    以下の【提供された記事データ】のみを基に、日本の読者向けに毎朝のニュース要約を作成してください。
    提供されていない情報を付け加えたり、嘘のURLを創作することは厳禁です。
    全体から「AI」「Python/コーディングTips」「コンサル/ビジネス」に関わる重要なトピックを厳選してください。

    【出力フォーマット】
    ■ [記事のタイトル]
      - 3行程度の具体的かつ実務にどう役立つかを含めた文章要約
      🔗 [リンク先URL]

    【提供された記事データ】
    {articles}
    """
    
    response = model.generate_content(prompt)
    return response.text

def send_to_line(text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        raise ValueError("LINEの認証情報が設定されていません。.envファイルを確認してください。")

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
    print("ニュースを取得中...")
    raw_articles = fetch_latest_articles()
    
    print("Geminiで要約を生成中...")
    summary_text = generate_summary(raw_articles)
    
    print("スマホのLINEへ送信中...")
    send_to_line(summary_text[:4900])
