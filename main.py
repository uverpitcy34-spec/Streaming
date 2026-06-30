```python
import os
import json
import re
import feedparser
import requests
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# .envファイルから環境変数（鍵）を読み込む
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# 💡 明示的に日本時間(JST)のタイムゾーンを定義してサーバーの国籍に依存させない
JST = timezone(timedelta(hours=9))

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

# 💡 経営・ビジネス情報に混ざるプライベート系ノイズ記事を完全にシャットアウトするキーワード群
EXCLUDE_KEYWORDS = [
    "| ライフ |", 
    "| エンタメ |", 
    "| カルチャー |", 
    "| スポーツ |", 
    "| 旅行 |", 
    "| グルメ |", 
    "| ファッション |", 
    "| コミック |",
    "芸能", "亀梨和也", "田中みな実", "結婚", "妊娠", "熱愛"
]

def clean_url(url_string):
    """URLからトラッキング用のクエリパラメータやフラグメントを削除して正規化する"""
    if not url_string:
        return ""
    try:
        parsed = urlparse(url_string.strip())
        kv_pairs = parse_qsl(parsed.query)
        # 不要なマーケティング用パラメータ(utm_*)を排除
        cleaned_kv = [(k, v) for k, v in kv_pairs if not k.startswith("utm_")]
        new_query = urlencode(cleaned_kv)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))
    except Exception:
        return url_string.strip()

def fetch_all_genres():
    structured_data = ""
    seen_links = set()
    
    # 日本時間ベースで5日前の足切りラインを算出
    now_jst = datetime.now(JST)
    time_threshold = now_jst - timedelta(hours=120)

    for genre_name, urls in GENRE_CHANNELS.items():
        structured_data += f"\n\n【{genre_name}】\n"
        genre_articles_count = 0
        
        for url in urls:
            try:
                feed = feedparser.parse(url)
                max_fetch = 15 if "5." in genre_name else 5
                
                for entry in feed.entries[:max_fetch]:
                    link = clean_url(entry.link)
                    if not link or link in seen_links:
                        continue
                    
                    title = entry.title.strip() if entry.title else "無題"
                    summary = entry.get("summary", "")[:250].strip()
                    summary = re.sub(r'\s+', ' ', summary)

                    # 💡 【ノイズフィルタ】タイトルまたは概要に除外キーワードが含まれる場合はGeminiに送らず完全スキップ
                    should_exclude = False
                    for kw in EXCLUDE_KEYWORDS:
                        if kw in title or kw in summary:
                            should_exclude = True
                            break
                    if should_exclude:
                        print(f"Skipped unwanted article (filtered): {title}")
                        continue
                    
                    # 記事の投稿日時を解析（表示用・およびフィルター用）
                    date_str = ""
                    published_tok = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published_tok:
                        try:
                            # タイムゾーンを考慮しない形(Naive)で一旦復元し、UTCとみなしてJSTに変換
                            dt_naive = datetime(*published_tok[:6])
                            dt_utc = dt_naive.replace(tzinfo=timezone.utc)
                            dt_jst = dt_utc.astimezone(JST)
                            
                            if dt_jst < time_threshold:
                                continue
                            date_str = dt_jst.strftime("%m/%d %H:%M")
                        except Exception:
                            pass
                    
                    # 日付が取れなかった場合のバックアップ表記
                    if not date_str:
                        date_str = "最近の投稿"
                    
                    seen_links.add(link)
                    
                    # Geminiへのインプット情報に「投稿日」も付与する
                    structured_data += f"- タイトル: {title}\n  URL: {link}\n  投稿日: {date_str}\n  概要: {summary}\n"
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
    2. 各記事のURL・投稿日は、データにあるものをそのまま完全に出力してください。
    3. 海外ソース（英語のタイトルや本文）は、必ず高度なビジネス日本語に翻訳した上で要約を行ってください。
    4. 💡 芸能、恋愛、結婚、健康、医療、美容、ペット、趣味、ライフハック、生活お悩み相談などの「プライベート・生活情報（特にタイトルに『ライフ』や『エンタメ』が含まれるもの）」は、ビジネスブリーフィングとしての質を保つために完全に除外・排除してください。

    【🔥 配信本数ルール（厳守）】
    ・「ai-domestic」「ai-overseas」「ai-tips」「dx-case」「consulting」の各ジャンル：各5〜6本目安
    ・「business」ジャンル：純粋な経済・経営・企業活動のニュースの中から、データがある限り妥協せず【20本目安】の大ボリュームで出力

    【出力形式の指定】
    指定された6つのキー（"ai-domestic", "ai-overseas", "ai-tips", "dx-case", "business", "consulting"）を最上位に持つJSONオブジェクトとして出力してください。
    各記事オブジェクトは "title", "url", "date", "summary" の4つのキーを持つ必要があります。"date"には提供データにある投稿日（例: "07/01 08:30"など）をそのまま入れてください。
    "summary" は3行程度の要約文の配列（文字列のリスト）としてください。

    【提供されたジャンル別・記事データ】
    {structured_articles_text}
    """
    
    # 古いライブラリバージョンでも完全にJSON構造をロックするスキーマ定義
    article_schema = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "url": {"type": "STRING"},
            "date": {"type": "STRING"},  # 日付用キーを追加
            "summary": {
                "type": "ARRAY",
                "items": {"type": "STRING"}
            }
        },
        "required": ["title", "url", "date", "summary"]
    }
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "ai-domestic": {"type": "ARRAY", "items": article_schema},
            "ai-overseas": {"type": "ARRAY", "items": article_schema},
            "ai-tips": {"type": "ARRAY", "items": article_schema},
            "dx-case": {"type": "ARRAY", "items": article_schema},
            "business": {"type": "ARRAY", "items": article_schema},
            "consulting": {"type": "ARRAY", "items": article_schema}
        },
        "required": ["ai-domestic", "ai-overseas", "ai-tips", "dx-case", "business", "consulting"]
    }
    
    response = model.generate_content(
        prompt, 
        generation_config={
            "response_mime_type": "application/json",
            "response_schema": response_schema
        }
    )
    return response.text

def create_html_site(json_text):
    json_text = json_text.strip()
    triple_backtick = "`" * 3
    if json_text.startswith(triple_backtick):
        json_text = re.sub(r'^`{3}(?:json)?\n', '', json_text)
        json_text = re.sub(r'\n`{3}$', '', json_text)
    json_text = json_text.strip()

    try:
        data = json.loads(json_text)
    except Exception as e:
        print(f"Error: JSONのパースに失敗しました。 {e}")
        data = {}
        
    normalized_data = {}
    for standard_key in ["ai-domestic", "ai-overseas", "ai-tips", "dx-case", "business", "consulting"]:
        possible_keys = [standard_key, standard_key.replace("-", "_"), standard_key.replace("_", "-")]
        articles = []
        for pk in possible_keys:
            if pk in data and isinstance(data[pk], list) and len(data[pk]) > 0:
                articles = data[pk]
                break
        normalized_data[standard_key] = articles
        
    # 💡 表示用のメインヘッダー日付を「2026年07月01日」のように正しく表示
    today_str = datetime.now(JST).strftime("%Y年%m月%d日")
    
    genre_html_dict = {}
    for genre_key in ["ai-domestic", "ai-overseas", "ai-tips", "dx-case", "business", "consulting"]:
        articles = normalized_data.get(genre_key, [])
        cards_html = ""
        
        if not articles:
            cards_html = '<p style="color:var(--text-muted); text-align:center; padding:20px;">（本日の新規投稿はありません）</p>'
        else:
            for art in articles:
                title_clean = str(art.get('title', '無題')).replace('"', '&quot;')
                url_clean = str(art.get('url', '#'))
                art_date = str(art.get('date', '最近の投稿'))
                
                summary_items = art.get("summary", [])
                if isinstance(summary_items, str):
                    summary_items = [summary_items]
                li_elements = "".join([f"<li>{str(item).replace('<', '&lt;')}</li>" for item in summary_items])
                
                # タイトルの下に小さく薄いグレーで投稿日（🕒 07/01 08:30）を表示
                cards_html += f"""
                <div class="news-card">
                    <div class="card-summary-trigger" onclick="toggleCard(this)">
                        <div class="title-block">
                            <h2 class="news-title">{title_clean}</h2>
                            <div class="news-date">🕒 {art_date}</div>
                        </div>
                        <svg class="icon-arrow" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
                    </div>
                    <div class="card-details">
                        <div class="card-details-inner">
                            <ul class="summary-list">
                                {li_elements}
                            </ul>
                            <a href="{url_clean}" target="_blank" class="btn-source">ソース元で記事を読む ↗</a>
                        </div>
                    </div>
                </div>
                """
        genre_html_dict[genre_key] = cards_html

    template_html = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Morning Briefing</title>
    <style>
        :root { --primary-color: #2563eb; --background-color: #f8fafc; --card-background: #ffffff; --text-main: #1e293b; --text-muted: #64748b; --border-color: #e2e8f0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background-color: var(--background-color); color: var(--text-main); margin: 0; padding: 0; line-height: 1.5; }
        header { background-color: var(--card-background); padding: 16px; text-align: center; border-bottom: 1px solid var(--border-color); position: sticky; top: 0; z-index: 100; }
        header h1 { margin: 0; font-size: 1.2rem; font-weight: 700; }
        header .date { font-size: 0.85rem; color: var(--text-muted); margin-top: 4px; }
        .nav-tabs-container { background-color: var(--card-background); border-bottom: 1px solid var(--border-color); position: sticky; top: 61px; z-index: 99; overflow-x: auto; white-space: nowrap; -webkit-overflow-scrolling: touch; }
        .nav-tabs-container::-webkit-scrollbar { display: none; }
        .tabs { display: inline-flex; padding: 0 8px; }
        .tab-btn { background: none; border: none; padding: 12px 16px; font-size: 0.9rem; font-weight: 600; color: var(--text-muted); cursor: pointer; position: relative; white-space: nowrap; }
        .tab-btn.active { color: var(--primary-color); }
        .tab-btn.active::after { content: ''; position: absolute; bottom: 0; left: 16px; right: 16px; height: 3px; background-color: var(--primary-color); border-radius: 2px; }
        main { padding: 16px; max-width: 600px; margin: 0 auto; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .news-card { background-color: var(--card-background); border: 1px solid var(--border-color); border-radius: 12px; margin-bottom: 12px; overflow: hidden; transition: box-shadow 0.2s; }
        .card-summary-trigger { padding: 16px; cursor: pointer; display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; user-select: none; }
        .card-summary-trigger:active { background-color: #f1f5f9; }
        .title-block { display: flex; flex-direction: column; gap: 4px; flex-grow: 1; }
        .news-title { margin: 0; font-size: 0.95rem; font-weight: 600; color: var(--text-main); line-height: 1.4; }
        .news-date { font-size: 0.75rem; color: var(--text-muted); font-weight: 500; }
        .icon-arrow { width: 20px; height: 20px; fill: var(--text-muted); transition: transform 0.2s; flex-shrink: 0; margin-top: 2px; }
        .card-details { max-height: 0; overflow: hidden; transition: max-height 0.25s ease-out; background-color: #fafafa; border-top: 0px solid var(--border-color); }
        .card-details-inner { padding: 16px; }
        .summary-list { margin: 0 0 16px 0; padding-left: 20px; font-size: 0.9rem; color: #334155; }
        .summary-list li { margin-bottom: 8px; }
        .summary-list li:last-child { margin-bottom: 0; }
        .btn-source { display: inline-flex; align-items: center; justify-content: center; width: 100%; padding: 10px; background-color: #f1f5f9; color: var(--primary-color); text-decoration: none; border-radius: 6px; font-size: 0.85rem; font-weight: 600; box-sizing: border-box; }
        .btn-source:active { background-color: #e2e8f0; }
        .news-card.open .icon-arrow { transform: rotate(180deg); }
        .news-card.open .card-details { border-top-width: 1px; }
    </style>
</head>
<body>
    <header>
        <h1>Private Briefing</h1>
        <div class="date">{{DATE}}</div>
    </header>
    <div class="nav-tabs-container">
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab(event, 'ai-domestic')">AI国内</button>
            <button class="tab-btn" onclick="switchTab(event, 'ai-overseas')">AI海外</button>
            <button class="tab-btn" onclick="switchTab(event, 'ai-tips')">実務Tips</button>
            <button class="tab-btn" onclick="switchTab(event, 'dx-case')">DX事例</button>
            <button class="tab-btn" onclick="switchTab(event, 'business')">経営・ビジネス</button>
            <button class="tab-btn" onclick="switchTab(event, 'consulting')">コンサル動向</button>
        </div>
    </div>
    <main>
        <div id="ai-domestic" class="tab-content active">{{AI_DOMESTIC}}</div>
        <div id="ai-overseas" class="tab-content">{{AI_OVERSEAS}}</div>
        <div id="ai-tips" class="tab-content">{{AI_TIPS}}</div>
        <div id="dx-case" class="tab-content">{{DX_CASE}}</div>
        <div id="business" class="tab-content">{{BUSINESS}}</div>
        <div id="consulting" class="tab-content">{{CONSULTING}}</div>
    </main>
    <script>
        function switchTab(event, tabId) {
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            event.currentTarget.classList.add('active');
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        function toggleCard(element) {
            const card = element.parentElement;
            const details = card.querySelector('.card-details');
            if (card.classList.contains('open')) {
                details.style.maxHeight = null;
                card.classList.remove('open');
            } else {
                details.style.maxHeight = details.scrollHeight + "px";
                card.classList.add('open');
            }
        }
    </script>
</body>
</html>"""

    final_html = template_html.replace("{{DATE}}", today_str)
    final_html = final_html.replace("{{AI_DOMESTIC}}", genre_html_dict["ai-domestic"])
    final_html = final_html.replace("{{AI_OVERSEAS}}", genre_html_dict["ai-overseas"])
    final_html = final_html.replace("{{AI_TIPS}}", genre_html_dict["ai-tips"])
    final_html = final_html.replace("{{DX_CASE}}", genre_html_dict["dx-case"])
    final_html = final_html.replace("{{BUSINESS}}", genre_html_dict["business"])
    final_html = final_html.replace("{{CONSULTING}}", genre_html_dict["consulting"])

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    print("index.html の生成に成功しました。")

def send_to_line():
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        raise ValueError("LINEの認証情報が設定されていません。")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    repository_full = os.getenv("GITHUB_REPOSITORY")
    
    if repository_full:
        parts = repository_full.split("/")
        github_user = parts[0].lower()
        repo_name = parts[1]
        
        if repo_name.lower() == f"{github_user}.github.io":
            site_url = f"https://{github_user}.github.io/"
        else:
            site_url = f"https://{github_user}.github.io/{repo_name}/"
    else:
        site_url = "https://github.com"
    
    # LINEに表示する配信日付も完全に日本時間(JST)ベース
    today_str = datetime.now(JST).strftime("%m/%d")

    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "flex",
                "altText": f"【{today_str}】朝のニュースサイトが更新されました",
                "contents": {
                  "type": "bubble",
                  "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                      {"type": "text", "text": "📰 Morning Briefing", "weight": "bold", "size": "xl", "color": "#1e293b"},
                      {"type": "text", "text": f"本日（{today_str}）の最新要約が専用サイトに届いています。下部ボタンよりご確認ください。", "margin": "md", "wrap": True, "color": "#64748b", "size": "sm"},
                      {"type": "button", "action": {"type": "uri", "label": "🚀 専用サイトを開く", "uri": site_url}, "style": "primary", "color": "#2563eb", "margin": "xl"}
                    ]
                  }
                }
            }
        ]
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"LINE送信エラー: {response.text}")
    else:
        print(f"LINEへの通知リンク送信が完了しました。送信URL: {site_url}")

if __name__ == "__main__":
    print("6つのジャンル別にRSSソースから重複を排除して取得中...")
    processed_data = fetch_all_genres()
    
    print("GeminiでJSON形式の要約データを生成中...")
    summary_json = generate_summary(processed_data)
    
    print("静的HTMLサイト(index.html)を構築中...")
    create_html_site(summary_json)
    
    print("スマホのLINEへ通知リンクを送信中...")
    send_to_line()

```
