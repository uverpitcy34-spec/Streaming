import os
import sys
import urllib.parse
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# ==========================================
# 4つの新しいカテゴリと検索クエリの定義
# ==========================================
CATEGORIES = {
    "AI動向・Tips": {
        "query": "AI トレンド OR LLM 開発 OR プロンプト 活用",
        "title": "🤖【最新AI動向 ＆ 実務Tips】"
    },
    "コンサルティング業界": {
        "query": "コンサルティングファーム OR マッキンゼー OR アクセンチュア OR コンサル キャリア",
        "title": "💼【コンサルティング業界 ニュース】"
    },
    "ビジネス・経営情報": {
        "query": "経済トレンド OR 経営戦略 OR ビジネス ニュース",
        "title": "📈【一般的なビジネス・経営情報】"
    },
    "生産性向上・仕事術": {
        "query": "業務効率化 OR 生産性向上 OR 時短 ワークフロー",
        "title": "⏱️【生産性向上・時短仕事術】"
    }
}

def fetch_google_news(category_key):
    cat_data = CATEGORIES.get(category_key)
    if not cat_data:
        return []
        
    query = f"{cat_data['query']} when:1d"
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    
    feed = feedparser.parse(rss_url)
    articles = []
    seen_domains = set()
    
    for entry in feed.entries:
        domain = entry.link.split("/")[2] if len(entry.link.split("/")) > 2 else ""
        
        # 1つのソースに偏らないよう、同じサイトからは最大3本まで
        if list(seen_domains).count(domain) >= 3:
            continue
            
        articles.append({
            "title": entry.title,
            "link": entry.link,
            "pubDate": entry.get("published", "")
        })
        seen_domains.add(domain)
        
        # 1ジャンル10本を確実に生成するため、元ネタは多めに「15本」確保
        if len(articles) >= 15:
            break
            
    return articles

def generate_summary(category_key, articles):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
        
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    cat_title = CATEGORIES[category_key]["title"]
    
    prompt = f"""
    あなたはプロのビジネスコンサルタント兼リサーチャーです。
    以下の【提供された最新記事データ】のみを基に、日本の読者向けに毎朝のニュース配信テキストを作成してください。

    【絶対厳守ルール】
    1. 提供されていない情報を付け加えてニュースを創作（ハルシネーション）することは厳禁です。
    2. 各記事のURL（link）は、提供されたものを1文字も変えずにそのまま出力してください。
    3. 送られてきたデータの中から、実務へのインパクトが大きいものを【必ずちょうど10本】厳選してください。元データが足りない場合のみ、ある分だけで出力してください。

    【出力フォーマット】
    {cat_title}

    ● [記事タイトル（無駄なサイト名などは削り、綺麗に整形）]
      - 3行程度で、なぜ今これを読むべきか、実務やキャリアにどう活きるかの要約
      🔗 [提供されたURLをそのまま記載]
      
    (※これを10本分、綺麗に並べて出力してください。各記事の間には空行を挟んで読みやすくしてください。)
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
    if response.status_code != 200:
        print(f"LINEエラー: {response.text}")

if __name__ == "__main__":
    # 引数から実行したいカテゴリ名を受け取る (例: python main.py "AI動向・Tips")
    if len(sys.argv) < 2:
        print("エラー: カテゴリを引数に指定してください。")
        sys.exit(1)
        
    target_category = sys.argv[1]
    if target_category not in CATEGORIES:
        print(f"エラー: 未定義のカテゴリです -> {target_category}")
        sys.exit(1)
        
    print(f"【{target_category}】の処理を開始します...")
    raw_articles = fetch_google_news(target_category)
    summary_text = generate_summary(target_category, raw_articles)
    
    # LINEの5000文字制限に収めて送信
    send_to_line(summary_text[:4900])
    print(f"【{target_category}】のLINE配信が完了しました。")
