import os
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
    提供された【ジャンル別・記事データ】から重要トピックを厳選し、指定の【配信本数ルール】を厳格に守って、日本の読者向けに毎朝のニュース配信テキストを作成してください。

    【絶対厳守ルール】
    1. 提供されたデータに実在しないニュース、存在しないURLは絶対に創作しないでください（ハルシネーションの徹底排除）。
    2. 各記事のURLは、データにあるものをそのまま完全に出力してください。
    3. 海外ソース（英語のタイトルや本文）は、必ず高度なビジネス日本語に翻訳した上で要約を行ってください。
    4. インプットのジャンルの枠組み（1〜6）の名称や順序を絶対に崩さないでください。

    【🔥 配信本数ルール（厳守）】
    ・「1」「2」「3」「4」および新設の「6. コンサルティング業界動向」：
       重要な情報に集中するため、特に有益なものを厳選して【各5〜6本目安】で出力してください。
    ・「5. 経営・ビジネス情報（日経等）」：
       ここがいけぽん様の最重要メインジャンルです。日経ビジネスや東洋経済等から、企業の広範な情報を網羅するため、データがある限り妥協せず【20本目安】の大ボリュームで圧倒的に手厚く出力してください。

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

    （ジャンル6まで美しいフォーマットで漏れなく出力。特にジャンル5は20本近く並ぶ形になります）
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
    
    # 経営・ビジネス情報が20本に増えて総文字数がさらに大きくなるため、4500文字ずつのブロックに小分けして確実に連続プッシュします
    max_length = 4500
    text_length = len(text)
    
    for i in range(0, text_length, max_length):
        chunk = text[i:i+max_length]
        
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": chunk}]
        }
        
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"LINE送信エラー: {response.text}")
            
    print("LINEへの配信処理が正常に完了しました。")

if __name__ == "__main__":
    print("6つのジャンル別にRSSソースから重複を排除して取得中...")
    processed_data = fetch_all_genres()
    
    print("Geminiでジャンルごとの本数を最適化（5番を20本、6番を新規追加）して要約を生成中...")
    summary_text = generate_summary(processed_data)
    
    print("スマホのLINEへ送信中...")
    send_to_line(summary_text)
