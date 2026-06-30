import os
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse

# .envファイルから環境変数（鍵）を読み込む
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# ── 【完全固定】6大ジャンル設計図 ──
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
        "https://business.nikkei.com/rss/bn/nb.rdf",
        "https://toyokeizai.net/list/feed/rss",
        "https://diamond.jp/rss/articles",
        "https://www.dhbr.net/rss"
    ],
    "6. コンサルティング業界動向": [
        "https://www.consulnews.jp/feed/"
    ]
}

def clean_url(url_string):
    """🔥【エラー原因解決】URLの前後にあるスペースや制御文字、改行を完全に排除する"""
    if not url_string:
        return ""
    # 前後の空白・改行を取り除く
    url = url_string.strip()
    # パースして正常なURL構造に再整形（不正な文字の混入を防ぐ）
    parsed = urlparse(url)
    return urlunparse(parsed)

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
                max_fetch = 15 if "5." in genre_name else 5
                
                for entry in feed.entries[:max_fetch]:
                    # 🔥URLのクレンジング処理を適用
                    link = clean_url(entry.link)
                    
                    if not link or link in seen_links:
                        continue
                    
                    published_tok = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published_tok:
                        published_dt = datetime(*published_tok[:6])
                        if published_dt < time_threshold:
                            continue
                    
                    seen_links.add(link)
                    title = entry.title.strip()
                    summary = entry.get("summary", "")[:250].strip()
                    
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
    提供された【ジャンル別・記事データ】から重要トピックを厳選し、日本の読者向けに毎朝のニュース配信テキストを作成してください。

    【🚨 最重要指示：URLの絶対厳守】
    データに記載されているURL（httpから始まる文字列）は、1文字も変更せず、末尾にスペースやドット(.)、改行コードなどを巻き込まずに、そのままの形で「単独の行」として出力してください。
    URLの文字列が汚れると、LINEでクリックした際にエラー画面になってしまいます。

    【配信本数ルール（厳守）】
    ・「1」「2」「3」「4」「6」：特に有益なものを厳選して【各5〜6本目安】
    - 「5. 経営・ビジネス情報（日経等）」：企業の広い情報を網羅するため【20本目安】

    【出力フォーマット】
    毎朝の情報収集お疲れ様です。本日は、コンサル実務に資する最新のAI・テクノロジー動向、経営ビジネス情報、およびコンサル業界に関する重要なトピックを厳選してお届けします。

    ---

    ■ 1. AI最新動向（国内）
    - [記事タイトル]
      要約文（3行程度で具体的かつ実務での価値を記述）
      🔗 [URL]

    ■ 2. AI最新動向（海外・英語）
    - [記事タイトル（日本語訳）]
      要約文（3行程度）
      🔗 [URL]

    （ジャンル6まで同様の美しいフォーマットで出力。URLの文字列の正確性を最優先してください）
    ---
    
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
    
    # 行単位で安全に分割し、URLの途中でメッセージが切れるのを防ぐ
    max_length = 4000
    lines = text.split("\n")
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 < max_length:
            current_chunk += line + "\n"
        else:
            payload = {
                "to": LINE_USER_ID,
                "messages": [{"type": "text", "text": current_chunk.strip()}]
            }
            requests.post(url, headers=headers, json=payload)
            current_chunk = line + "\n"
            
    if current_chunk.strip():
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": current_chunk.strip()}]
        }
        requests.post(url, headers=headers, json=payload)
            
    print("LINEへの配信処理が正常に完了しました。")

if __name__ == "__main__":
    processed_data = fetch_all_genres()
    summary_text = generate_summary(processed_data)
    send_to_line(summary_text)
