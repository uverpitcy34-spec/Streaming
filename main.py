import os
import json  # 追加
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
# （ここは変更なしのため中略します）
GENRE_CHANNELS = { ... }

def fetch_all_genres():
    # （ここは変更なしのため中略します）
    ...

def generate_summary(structured_articles_text):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY が設定されていません。")
        
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # 💡 修正ポイント: Pythonでパースしやすいように「JSON形式」で出力させます
    prompt = f"""
    あなたはプロフェッショナルなコンサルタントの右腕となる、非常に優秀なシニアリサーチャーです。
    提供された【ジャンル別・記事データ】から重要トピックを厳選し、指定の【配信本数ルール】を厳格に守って、日本の読者向けにニュースデータを抽出・翻訳・要約してください。

    【絶対厳守ルール】
    1. 提供されたデータに実在しないニュース、存在しないURLは絶対に創作しないでください（ハルシネーションの徹底排除）。
    2. 各記事のURLは、データにあるものをそのまま完全に出力してください。
    3. 海外ソース（英語のタイトルや本文）は、必ず高度なビジネス日本語に翻訳した上で要約を行ってください。

    【🔥 配信本数ルール（厳守）】
    ・「ai-domestic」「ai-overseas」「ai-tips」「dx-case」「consulting」：
       重要な情報に集中するため、特に有益なものを厳選して【各5〜6本目安】で出力してください。
    ・「business」：
       ここがいけぽん様の最重要メインジャンルです。日経ビジネスや東洋経済等から、企業の広範な情報を網羅するため、データがある限り妥協せず【20本目安】の大ボリュームで手厚く出力してください。

    【出力フォーマット】
    必ず以下のキーを持つ純粋なJSON形式で出力してください。バッククォートなどの余計な装飾は不要です。
    ジャンル名のキーは「ai-domestic」「ai-overseas」「ai-tips」「dx-case」「business」「consulting」の6つとしてください。

    {{
      "ai-domestic": [
        {{
          "title": "記事タイトル1",
          "url": "https://...",
          "summary": ["要約ポイント1", "要約ポイント2", "要約ポイント3"]
        }}
      ],
      "ai-overseas": [ ... ],
      "ai-tips": [ ... ],
      "dx-case": [ ... ],
      "business": [ ... ],
      "consulting": [ ... ]
    }}
    
    【提供されたジャンル別・記事データ】
    {structured_articles_text}
    """
    
    # JSONとして厳格に出力させる設定
    response = model.generate_content(
        prompt, 
        generation_config={"response_mime_type": "application/json"}
    )
    return response.text

# 💡 新設: Playcodeで作成したテンプレートにJSONデータを流し込んで index.html を作る関数
def create_html_site(json_text):
    data = json.loads(json_text)
    today_str = datetime.now().strftime("%Y年%m%d日")
    
    # 各ジャンルのカードHTMLを組み立てる
    genre_html_dict = {}
    for genre_key in ["ai-domestic", "ai-overseas", "ai-tips", "dx-case", "business", "consulting"]:
        articles = data.get(genre_key, [])
        cards_html = ""
        
        if not articles:
            cards_html = '<p style="color:var(--text-muted); text-align:center; padding:20px;">（本日の新規投稿はありません）</p>'
        else:
            for art in articles:
                li_elements = "".join([f"<li>{item}</li>" for item in art.get("summary", [])])
                cards_html += f"""
                <div class="news-card">
                    <div class="card-summary-trigger" onclick="toggleCard(this)">
                        <h2 class="news-title">{art.get('title')}</h2>
                        <svg class="icon-arrow" viewBox="0 0 24 24"><path d="M7 10l5 5 5-5z"/></svg>
                    </div>
                    <div class="card-details">
                        <div class="card-details-inner">
                            <ul class="summary-list">
                                {li_elements}
                            </ul>
                            <a href="{art.get('url')}" target="_blank" class="btn-source">ソース元で記事を読む ↗</a>
                        </div>
                    </div>
                </div>
                """
        genre_html_dict[genre_key] = cards_html

    # Playcodeで固めたHTMLの「ガワ」
    # 💡 変化する日付や各コンテンツの部分をプレースホルダー（ {{...}} ）に書き換えています
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
        .news-title { margin: 0; font-size: 0.95rem; font-weight: 600; color: var(--text-main); flex-grow: 1; }
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
            <button class="tab-btn active" onclick="switchTab('ai-domestic')">AI国内</button>
            <button class="tab-btn" onclick="switchTab('ai-overseas')">AI海外</button>
            <button class="tab-btn" onclick="switchTab('ai-tips')">実務Tips</button>
            <button class="tab-btn" onclick="switchTab('dx-case')">DX事例</button>
            <button class="tab-btn" onclick="switchTab('business')">経営・ビジネス</button>
            <button class="tab-btn" onclick="switchTab('consulting')">コンサル動向</button>
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
        function switchTab(tabId) {
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

    # データをテンプレートに流し込む
    final_html = template_html.replace("{{DATE}}", today_str)
    final_html = final_html.replace("{{AI_DOMESTIC}}", genre_html_dict["ai-domestic"])
    final_html = final_html.replace("{{AI_OVERSEAS}}", genre_html_dict["ai-overseas"])
    final_html = final_html.replace("{{AI_TIPS}}", genre_html_dict["ai-tips"])
    final_html = final_html.replace("{{DX_CASE}}", genre_html_dict["dx-case"])
    final_html = final_html.replace("{{BUSINESS}}", genre_html_dict["business"])
    final_html = final_html.replace("{{CONSULTING}}", genre_html_dict["consulting"])

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
    print("index.htmlの生成に成功しました。")

# 💡 修正ポイント: 長文の代わりに、生成されたWebサイトへの案内リンク（Flex Message風）を1通だけ送る
def send_to_line():
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        raise ValueError("LINEの認証情報が設定されていません。")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    # 💡 ご自身のGitHubユーザー名とリポジトリ名に書き換えてください
    github_user = "YOUR_GITHUB_USERNAME"
    repo_name = "YOUR_REPO_NAME"
    site_url = f"https://{github_user}.github.io/{repo_name}/"
    
    today_str = datetime.now().strftime("%m/%d")

    # シンプルで見やすいFlex Messageを送信
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
        print("LINEへの通知リンク送信が完了しました。")

if __name__ == "__main__":
    print("6つのジャンル別にRSSソースから重複を排除して取得中...")
    processed_data = fetch_all_genres()
    
    print("GeminiでJSON形式の要約データを生成中...")
    summary_json = generate_summary(processed_data)
    
    print("静的HTMLサイト(index.html)を構築中...")
    create_html_site(summary_json)
    
    print("スマホのLINEへ通知リンクを送信中...")
    send_to_line()
