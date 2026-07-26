import os
import json
import re
import feedparser
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# 最新のGoogle GenAI SDKを使用
from google import genai
from google.genai import types

# .envファイルから環境変数（APIキー等）を読み込む
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")

# 日本時間(JST)のタイムゾーンを定義
JST = timezone(timedelta(hours=9))

# ── 【6大ジャンル設計図と内部キーの対応（フィードを追加・拡充）】 ──
GENRE_CONFIG = [
    {
        "key": "ai-domestic",
        "name": "1. AI最新動向（国内）",
        "urls": [
            "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml",
            "https://www.publickey1.jp/atom.xml",
            "https://ascii.jp/rss/rss_ai.xml",
            "https://b.hatena.ne.jp/entrylist/it/ai.rss",  # 追加: はてなブックマークAI
            "https://ledge.ai/feed"                          # 追加: Ledge.ai
        ]
    },
    {
        "key": "ai-overseas",
        "name": "2. AI最新動向（海外・英語）",
        "urls": [
            "https://techcrunch.com/category/artificial-intelligence/feed/",
            "https://venturebeat.com/category/ai/feed/",
            "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            "https://mittechnologypreview.jp/tag/ai/feed/"  # 追加: MIT Tech Review
        ]
    },
    {
        "key": "ai-tips",
        "name": "3. AI実務Tips・Python・データサイエンス",
        "urls": [
            "https://qiita.com/tags/ai/feed",
            "https://qiita.com/tags/langchain/feed",
            "https://qiita.com/tags/python/feed",
            "https://qiita.com/tags/datascience/feed",
            "https://qiita.com/tags/machine-learning/feed",
            "https://zenn.dev/topics/llm/feed",
            "https://zenn.dev/topics/ai/feed",
            "https://zenn.dev/topics/python/feed",
            "https://zenn.dev/topics/datascience/feed",
            "https://b.hatena.ne.jp/entrylist/it/python.rss"  # 追加: はてブPython
        ]
    },
    {
        "key": "dx-case",
        "name": "4. 企業DX・IT導入事例",
        "urls": [
            "https://enterprisezine.jp/rss/new/",
            "https://japan.zdnet.com/rss/",
            "https://xtech.nikkei.com/rss/index.rdf",
            "https://rss.itmedia.co.jp/rss/2.0/business.xml",
            "https://b.hatena.ne.jp/entrylist/it/dx.rss"      # 追加: はてブDX
        ]
    },
    {
        "key": "business",
        "name": "5. 経営・ビジネス情報（日経等）",
        "urls": [
            "https://business.nikkei.com/rss/bn/nb.rdf",
            "https://toyokeizai.net/list/feed/rss",
            "https://diamond.jp/rss/articles",
            "https://www.dhbr.net/rss",
            "https://b.hatena.ne.jp/entrylist/economics.rss"  # 追加: はてブ経済
        ]
    },
    {
        "key": "consulting",
        "name": "6. コンサルティング業界動向",
        "urls": [
            "https://www.consulnews.jp/feed/",
            "https://ascii.jp/rss/rss_business.xml",
            "https://rss.itmedia.co.jp/rss/2.0/enterprise.xml"
        ]
    }
]

# 除外キーワードリスト
EXCLUDE_KEYWORDS = [
    "| ライフ |", "| キャリア |", "| エンタメ |", "| カルチャー |", "| スポーツ |", 
    "| 旅行 |", "| グルメ |", "| ファッション |", "| コミック |", "| 恋愛・結婚 |",
    "芸能", "亀梨和也", "田中みな実", "結婚", "妊娠", "熱愛", "占い", "レシピ", "美容"
]

def clean_url(url_string):
    """URLからトラッキングパラメータを削除して正規化"""
    if not url_string:
        return ""
    try:
        parsed = urlparse(url_string.strip())
        kv_pairs = parse_qsl(parsed.query)
        cleaned_kv = [(k, v) for k, v in kv_pairs if not k.startswith("utm_")]
        new_query = urlencode(cleaned_kv)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, ""))
    except Exception:
        return url_string.strip()

def fetch_articles_for_genre(urls):
    """指定されたフィード一覧から過去7日間の記事を取得"""
    seen_links = set()
    genre_articles = []
    
    now_jst = datetime.now(JST)
    time_threshold = now_jst - timedelta(days=7)

    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:  # 全エントリを取得
                link = clean_url(entry.link)
                if not link or link in seen_links:
                    continue
                
                title = entry.title.strip() if entry.title else "無題"
                summary = entry.get("summary", "")[:250].strip()
                summary = re.sub(r'\s+', ' ', summary)

                if any(kw in title or kw in summary for kw in EXCLUDE_KEYWORDS):
                    continue
                
                dt_jst = None
                date_str = ""
                published_tok = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_tok:
                    try:
                        dt_naive = datetime(*published_tok[:6])
                        dt_utc = dt_naive.replace(tzinfo=timezone.utc)
                        dt_jst = dt_utc.astimezone(JST)
                        
                        # 過去7日以内の記事のみを通過させる
                        if dt_jst < time_threshold:
                            continue
                        date_str = dt_jst.strftime("%m/%d %H:%M")
                    except Exception:
                        pass
                
                if not date_str:
                    date_str = "最近の投稿"
                    dt_jst = now_jst - timedelta(days=3)
                
                seen_links.add(link)
                genre_articles.append({
                    "title": title,
                    "url": link,
                    "date_str": date_str,
                    "dt_jst": dt_jst,
                    "summary": summary
                })
        except Exception as e:
            print(f"Warning: Failed to parse {url}. Error: {e}")
            continue
            
    # 投稿日時の新しい順（降順）にソート
    genre_articles.sort(key=lambda x: x["dt_jst"], reverse=True)
    return genre_articles

def summarize_single_genre(client, genre_name, articles):
    """1つのカテゴリーごとにGemini APIで要約・翻訳を生成"""
    if not articles:
        return []

    # テキストデータの作成
    articles_text = ""
    for art in articles:
        articles_text += f"- タイトル: {art['title']}\n  URL: {art['url']}\n  投稿日: {art['date_str']}\n  概要: {art['summary']}\n"

    prompt = f"""
    あなたはビジネスニュースの分析プロフェッショナルです。
    提供された【{genre_name}】の記事リストから、**全件（最大70件まで）**を要約・翻訳して出力してください。

    【絶対厳守ルール】
    1. **データを間引かないでください**。提供された記事データから条件に合うものは可能な限りすべて出力してください（最大70件）。
    2. 提供データに存在しないURLやタイトルは絶対に捏造しないでください。
    3. URLと投稿日（date）はデータにあるものをそのまま使用してください。
    4. 英語のタイトル・概要は、必ず【自然で高品質なビジネス日本語に翻訳】してください。
    5. 各記事の要約（summary）は、箇条書き2行（文字列の配列）で簡潔に記述してください。
    6. 投稿日が新しい順（降順）に並べて出力してください。

    【対象データ（計 {len(articles)} 件）】
    {articles_text}
    """

    article_schema = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "url": {"type": "STRING"},
            "date": {"type": "STRING"},
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
            "articles": {
                "type": "ARRAY",
                "items": article_schema
            }
        },
        "required": ["articles"]
    }

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema
            )
        )
        res_json = json.loads(response.text)
        return res_json.get("articles", [])
    except Exception as e:
        print(f"Gemini generation error for {genre_name}: {e}")
        return []

def generate_all_summaries():
    """全カテゴリーを順次処理して結合"""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
        
    client = genai.Client(api_key=GEMINI_API_KEY)
    final_data = {}

    for config in GENRE_CONFIG:
        key = config["key"]
        name = config["name"]
        urls = config["urls"]
        
        print(f"[{name}] の記事を取得中...")
        raw_articles = fetch_articles_for_genre(urls)
        print(f"  └ 過去7日間の該当記事: {len(raw_articles)}件 -> Geminiで処理中...")
        
        # 最大70件にスライスしてGeminiに渡す
        target_articles = raw_articles[:70]
        summarized = summarize_single_genre(client, name, target_articles)
        final_data[key] = summarized
        print(f"  └ 出力完了: {len(summarized)}件")

    return final_data

def create_html_site(data):
    """取得・要約したデータをHTML形式で出力"""
    today_str = datetime.now(JST).strftime("%Y年%m月%d日")
    genre_html_dict = {}

    for config in GENRE_CONFIG:
        genre_key = config["key"]
        articles = data.get(genre_key, [])
        cards_html = ""
        
        if not articles:
            cards_html = '<p style="color:var(--text-muted); text-align:center; padding:20px;">（過去1週間の新規投稿はありません）</p>'
        else:
            cards_html += f'<div style="margin-bottom:12px; font-size:0.85rem; color:var(--text-muted); text-align:right;">表示件数: {len(articles)}件（過去7日間）</div>'
            for art in articles:
                title_clean = str(art.get('title', '無題')).replace('"', '&quot;').replace('<', '&lt;')
                url_clean = str(art.get('url', '#'))
                art_date = str(art.get('date', '最近の投稿'))
                
                summary_items = art.get("summary", [])
                if isinstance(summary_items, str):
                    summary_items = [summary_items]
                li_elements = "".join([f"<li>{str(item).replace('<', '&lt;')}</li>" for item in summary_items])
                
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
                            <a href="{url_clean}" target="_blank" rel="noopener noreferrer" class="btn-source">ソース元で記事を読む ↗</a>
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
    final_html = final_html.replace("{{AI_DOMESTIC}}", genre_html_dict.get("ai-domestic", ""))
    final_html = final_html.replace("{{AI_OVERSEAS}}", genre_html_dict.get("ai-overseas", ""))
    final_html = final_html.replace("{{AI_TIPS}}", genre_html_dict.get("ai-tips", ""))
    final_html = final_html.replace("{{DX_CASE}}", genre_html_dict.get("dx-case", ""))
    final_html = final_html.replace("{{BUSINESS}}", genre_html_dict.get("business", ""))
    final_html = final_html.replace("{{CONSULTING}}", genre_html_dict.get("consulting", ""))

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    print("index.html の生成に成功しました。")

def send_to_line():
    """LINE Messaging APIへ通知を送信"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("LINE認証情報がないため送信をスキップします。")
        return

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
    print("=== カテゴリー別要約処理を開始 ===")
    summarized_data = generate_all_summaries()
    
    print("\n=== 静的HTML (index.html) の構築 ===")
    create_html_site(summarized_data)
    
    print("\n=== LINEへのプッシュ通知 ===")
    send_to_line()