import os
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time

# .envファイルから環境変数を読み込む
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# ── 【設計図】ジャンルごとのRSSフィード設定 ──
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
    seen_links = set()
    
    # 直近24時間以内の記事のみを対象にする基準時刻 (JST)
    now = datetime.now()
    time_threshold = now - timedelta(hours=24)

    for genre_name, urls in GENRE_CHANNELS.items():
        structured_data += f"\n\n【{genre_name}】\n"
        genre_articles_count = 0
        
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    link = entry.link
                    
                    # URLベースの絶対重複排除
                    if link in seen_links:
                        continue
                    
                    # 簡易的な日付チェック（24時間以内、取れない場合はプールを維持するため通す）
                    published_tok = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published_tok:
                        published_dt = datetime(*published_tok[:6])
                        if published_dt < time_threshold:
                            continue # 24時間以上前の古い記事はスキップ
                    
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
    あなたはプロフェッショナルなコンサルタントの右腕となる、非常に優秀なシニアリサーチャーです。
    提供された【ジャンル別・記事データ】の構造を完全に維持したまま、日本の読者向けに毎朝のニュース配信テキストを作成してください。

    【絶対厳守ルール】
    1. 提供されたデータに実在しないニュース、存在しないURLは絶対に創作しないでください（ハルシネーションの徹底排除）。
    2. 各記事のURLは、データにあるものをそのまま完全に出力してください。
    3. 海外ソース（英語のタイトルや本文）は、必ず高度なビジネス日本語に翻訳した上で要約を行ってください。
    4. インプットのジャンルの枠組み（1〜5）を絶対に崩さないでください。
    
    【区切りのルール】※重要
    各ジャンルの見出しの先頭には、必ず「■ 1. 」「■ 2. 」のように「■」をつけて出力してください。このマークを基準に後段でメッセージを分割します。

    【出力フォーマット】
    ■ 1. AI最新動向（国内）
    - [記事タイトル]
      要約文（3行程度で具体的かつ実務での価値を記述）
      🔗 [URL]

    ■ 2. AI最新動向（海外・英語）
    - [記事タイトル（日本語訳）]
      要約文（3行程度）
      🔗 [URL]

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
    
    # 🔥 【修正の核心】全体テキストを「■」の区切りごとに分割して、個別のメッセージとして送る
    # これにより文字数制限（5000文字）を回避し、ジャンルごとに個別のバルーンで届くようになります
    chunks = text.split("■")
    
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
            
        # 先頭に削られた「■」を復活させる
        formatted_message = "■ " + chunk
        
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": formatted_message[:4900]}]
        }
        
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"LINE送信エラー: {response.text}")
        
        # LINE APIの連続叩きによる一時エラー(一気送りのペナルティ)を防ぐため、1秒のウェイトを置く
        time.sleep(1)
        
    print("LINEへのジャンル別分割配信が完了しました。")

if __name__ == "__main__":
    print("5つのジャンル別にRSSソースから重複を排除して取得中...")
    processed_data = fetch_all_genres()
    
    print("Geminiでジャンル構造を維持したまま、翻訳・要約を生成中...")
    summary_text = generate_summary(processed_data)
    
    print("スマホのLINEへ分割送信を開始...")
    send_to_line(summary_text)
