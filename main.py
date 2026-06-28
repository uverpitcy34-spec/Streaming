import os
import urllib.parse
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv

# .envファイル（ローカル用）やGitHub Secretsからの環境変数読み込み
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# ==========================================
# 1. Googleニュースの検索RSSを使った、網羅的な情報収集
# ==========================================
def fetch_google_news_by_keyword(keyword):
    """
    指定したキーワードでGoogleニュースを検索し、
    過去24時間以内（when:1d）の最新記事を取得する
    """
    # 検索クエリをURLエンコード（日本語対応）
    # when:1d = 過去24時間以内、hl=ja = 日本語、gl=JP = 日本地域
    query = f"{keyword} when:1d"
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
    
    feed = feedparser.parse(rss_url)
    articles = []
    seen_domains = set() # 同じドメイン（サイト）ばかりになるのを防ぐカウンター
    
    for entry in feed.entries:
        # Googleニュースのリンク先からおおよそのドメインを取得（簡易的な重複排除）
        domain = entry.link.split("/")[2] if len(entry.link.split("/")) > 2 else ""
        
        # 同じサイトからは、1つのキーワードにつき最大2本までしか拾わないように制限
        if list(seen_domains).count(domain) >= 2:
            continue
            
        articles.append({
            "title": entry.title,
            "link": entry.link,
            "pubDate": entry.get("published", "")
        })
        seen_domains.add(domain)
        
        # 1つのキーワードにつき、上位7本集まったら終了（全カテゴリ合算でGeminiの処理上限に収めるため）
        if len(articles) >= 7:
            break
            
    return articles

def get_all_category_news():
    # コンサル実務・テックに特化した、Web全体を網羅するための4つの検索ワード
    categories = {
        "AI・LLM動向": "AI トレンド OR LLM 活用",
        "Python・Tech Tips": "Python 効率化 OR 開発 チュートリアル",
        "DX・ITコンサル": "DX 事例 OR ITコンサルティング",
        "ビジネス・生産性向上": "業務効率化 ツール OR 生産性向上"
    }
    
    all_news_data = {}
    for cat_name, query_str in categories.items():
        print(f"【{cat_name}】の最新ニュースをWeb全体から探索中...")
        all_news_data[cat_name] = fetch_google_news_by_keyword(query_str)
        
    return all_news_data

# ==========================================
# 2. Gemini 2.5 Flashによる、コンサル流の厳格な要約
# ==========================================
def generate_summary(all_news_data):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。GitHubのSecretsまたは.envを確認してください。")
        
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    あなたは優秀なビジネスコンサルタント兼テックリードの助手です。
    以下の【提供されたカテゴリ別の最新記事データ】のみを基に、日本の実務家向けに毎朝のニュース配信テキストを作成してください。

    【絶対厳守ルール】
    1. 提供されていない情報を付け加えてニュースを創作（ハルシネーション）することは厳禁です。
    2. 各記事のURL（link）は、提供されたものを1文字も変えずにそのまま出力してください。嘘のURLを作らないでください。
    3. 各カテゴリから、実務のヒントや効率化に直結する最も重要・有益な記事を最大3〜4本厳選し、他は削ってください。

    【出力フォーマット（LINE通知用）】
    【朝のAI・ビジネストレンド】

    ■ [カテゴリ名（例：AI・LLM動向）]
      ● [記事タイトル（パッと見で中身がわかるよう綺麗に整形）]
        - 3行程度で、なぜ今これを読むべきか、実務にどう活きるかの要約
        🔗 [提供されたURLをそのまま記載]

    【提供されたカテゴリ別の最新記事データ】
    {all_news_data}
    """
    
    response = model.generate_content(prompt)
    return response.text

# ==========================================
# 3. LINEへのプッシュ通知
# ==========================================
def send_to_line(text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        raise ValueError("LINEの認証情報が設定されていません。GitHubのSecretsまたは.envを確認してください。")

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

# ==========================================
# メイン処理
# ==========================================
if __name__ == "__main__":
    raw_data = get_all_category_news()
    
    print("GeminiでWeb全体のニュースから厳選・要約中...")
    summary_text = generate_summary(raw_data)
    
    print("スマホのLINEへ送信中...")
    # LINEの5000文字制限に安全に収める
    send_to_line(summary_text[:4900])
