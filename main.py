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

# 【精査＆網羅版】Claudeと共同作成した最強の全20フィード
RSS_URLS = [
    # ── 1. AI最新動向（国内）──
    "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",       # ITmedia AI++
    "https://www.publickey1.jp/atom.xml",                  # Publickey
    "https://ascii.jp/rss/rss_ai.xml",                     # ASCII.jp AI

    # ── 2. AI最新動向（海外・英語）──
    "https://techcrunch.com/category/artificial-intelligence/feed/",  # TechCrunch AI
    "https://venturebeat.com/category/ai/feed/",           # VentureBeat AI
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", # The Verge AI

    # ── 3. AI実務Tips・Pythonコーディング ──
    "https://qiita.com/tags/ai/feed",                      # Qiita AI
    "https://qiita.com/tags/langchain/feed",               # Qiita LangChain
    "https://qiita.com/tags/python/feed",                  # Qiita Python
    "https://zenn.dev/topics/llm/feed",                    # Zenn LLM
    "https://zenn.dev/topics/ai/feed",                     # Zenn AI
    "https://zenn.dev/topics/python/feed",                  # Zenn Python

    # ── 4. 企業DX・IT導入事例 ──
    "https://enterprisezine.jp/rss/new/",                  # EnterpriseZine
    "https://japan.zdnet.com/rss/",                        # ZDNET Japan
    "https://xtech.nikkei.com/rss/index.rdf",              # 日経XTECH
    "https://rss.itmedia.co.jp/rss/2.0/business.xml",      # ITmedia ビジネス

    # ── 5. 経営戦略・コンサル ──
    "https://www.dhbr.net/rss",                            # Harvard Business Review日本版
    "https://toyokeizai.net/list/feed/rss",                # 東洋経済オンライン
    "https://diamond.jp/rss/articles",                     # ダイヤモンドオンライン
    "https://business.nikkei.com/rss/bn/nb.rdf",           # 日経ビジネス
]

def fetch_latest_articles():
    articles = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            # 20フィードあるため、各ソースから最新3本ずつを厳選（総数最大60本程度）
            for entry in feed.entries[:3]:
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.get("summary", "")[:250]
                })
        except Exception as e:
            print(f"Warning: Failed to parse {url}. Error: {e}")
            continue
    return articles

def generate_summary(articles):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
        
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
    あなたはプロフェッショナルなコンサルタントの右腕となる、極めて優秀なシニアリサーチャーです。
    提供された【記事データ】のみを100%の正確な情報源として扱い、日本の読者向けに毎朝のニュース要約を作成してください。

    【絶対厳守ルール】
    1. 提供されたデータにないニュース、存在しないURLは1文字たりとも創作してはいけません（ハルシネーションの徹底排除）。
    2. 各記事のURL（link）は、データにあるものをそのまま完全に出力してください。ダミーURLへの置換は厳禁です。
    3. 【翻訳の義務】海外ソース（英語のタイトルや本文）が含まれている場合は、必ず高度なビジネス日本語に翻訳した上で要約を行ってください。

    【重要視するジャンル仕分け・選定の基準】
    ・AI動向：国内外（TechCrunch/VentureBeat等含む）の先端LLM・プロダクトの動向
    ・AI実務Tips：PythonやLangChain等を用いた、具体的なAI実装・自動化・コーディングの手法
    ・企業DX・生産性向上：「個人のタスク管理術」などは除外し、「企業や組織」がテクノロジーを導入してどのように業務プロセス（BPR）を刷新し、生産性を向上させたかの具体的事例を最優先にしてください。
    ・経営戦略：マクロな経済動向、経営戦略、組織論のインサイト

    【出力フォーマット】
    ■ [記事のタイトル（英語の場合は日本語訳）]
      - 3行程度の具体的かつ実務にどう役立つかを含めた文章要約
      🔗 [リンク先URL]

    【提供された記事データ】
    {articles}
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
    print("精査された20個のRSSソースから網羅的に記事を取得中...")
    raw_articles = fetch_latest_articles()
    
    if not raw_articles:
        send_to_line("📢 本日の最新ニュース・Tipsの更新はありませんでした。")
        exit()
        
    print(f"計 {len(raw_articles)} 本の記事をプール。Geminiで翻訳・仕分け・3行要約を生成中...")
    summary_text = generate_summary(raw_articles)
    
    print("スマホのLINEへ送信中...")
    # LINEの1メッセージの文字数制限（5000文字）に収まるよう安全にカット
    send_to_line(summary_text[:4900])
