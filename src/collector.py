import os
import re
import json
import feedparser
import requests
from datetime import datetime, timezone

NOTION_TOKEN    = os.getenv("NOTION_TOKEN")
DATABASE_ID     = os.getenv("NOTION_DATABASE_ID")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

ROUTE_KEYWORDS = {
    "중국→카자흐스탄":      ["kazakhstan", "kazakh", "ktz", "almaty", "nur-sultan", "astana", "horgos", "khorgos"],
    "중국→우즈베키스탄":    ["uzbekistan", "uzbek", "uty", "tashkent"],
    "중국→키르기스스탄":    ["kyrgyzstan", "kyrgyz", "bishkek", "torugart"],
    "중국→투르크메니스탄":  ["turkmenistan", "turkmen", "ashgabat"],
    "중국→러시아(TSR)":     ["russia", "tsr", "trans-siberian", "zabaykalsk", "naushki"],
    "한국/일본→중앙아시아": ["busan", "lianyungang", "korea", "japan"],
}

CATEGORY_KEYWORDS = {
    "운임동향":  ["freight rate", "tariff", "rate", "price", "cost", "fare"],
    "정책/규제": ["sanction", "policy", "regulation", "ban", "restriction"],
    "국경/통관": ["border", "customs", "crossing", "congestion", "delay"],
    "인프라":    ["infrastructure", "railway", "terminal", "port", "corridor"],
    "시장분석":  ["market", "analysis", "forecast", "demand", "supply", "outlook"],
}

CARGO_KEYWORDS = {
    "컨테이너(FCL)": ["fcl", "full container", "20ft", "40ft", "teu"],
    "컨테이너(LCL)": ["lcl", "less than container", "groupage"],
    "자동차/중장비":  ["automotive", "vehicle", "heavy equipment", "machinery"],
}

RSS_FEEDS = [
    {"url": "https://www.railwaysupply.net/rss",      "name": "Railway Supply"},
    {"url": "https://www.silkroadbriefing.com/feed/", "name": "Silk Road Briefing"},
    {"url": "https://theloadstar.com/feed/",          "name": "The Loadstar"},
    {"url": "https://splash247.com/feed/",            "name": "Splash247"},
    {"url": "https://www.chinafreightnews.com/feed",  "name": "China Freight News"},
    {"url": "https://eurasianet.org/feed",            "name": "Eurasianet"},
]


def get_today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def classify(text, keyword_map):
    text_lower = text.lower()
    return [tag for tag, kws in keyword_map.items() if any(k in text_lower for k in kws)]


def is_central_asia_related(text):
    all_kws = [kw for kws in ROUTE_KEYWORDS.values() for kw in kws]
    general = [
        "central asia", "silk road", "eurasian", "belt and road", "bri",
        "china rail", "trans-caspian", "middle corridor", "freight", "logistics",
    ]
    return any(kw in text.lower() for kw in all_kws + general)


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def translate_to_korean(title, summary):
    """Claude API로 제목과 요약을 한국어로 번역"""
    if not ANTHROPIC_KEY:
        print("  [번역 생략] ANTHROPIC_API_KEY 없음")
        return title, summary

    prompt = f"""다음 물류/운임 뉴스를 한국어로 번역해주세요.
물류, 철도, 해운 전문 용어는 정확하게 번역하고, 자연스러운 한국어로 작성해주세요.
반드시 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.

제목: {title}
요약: {summary}

응답 형식:
{{"제목": "번역된 제목", "요약": "번역된 요약"}}"""

    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if res.status_code == 200:
            raw = res.json()["content"][0]["text"].strip()
            data = json.loads(raw)
            print(f"  ✅ 번역 완료: {data['제목'][:40]}")
            return data["제목"], data["요약"]
        else:
            print(f"  ⚠️ 번역 API 오류: {res.status_code}")
            return title, summary
    except Exception as e:
        print(f"  ⚠️ 번역 실패: {e}")
        return title, summary


def fetch_articles():
    articles = []
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            print(f"[{feed_info['name']}] {len(feed.entries)}건 수집")
            for entry in feed.entries[:10]:
                title    = entry.get("title", "")
                summary  = strip_html(entry.get("summary", ""))
                link     = entry.get("link", "")
                combined = f"{title} {summary}"
                if not is_central_asia_related(combined):
                    continue
                articles.append({
                    "title":    title,
                    "summary":  summary[:500] if summary else "",
                    "url":      link,
                    "source":   feed_info["name"],
                    "routes":   classify(combined, ROUTE_KEYWORDS),
                    "category": (classify(combined, CATEGORY_KEYWORDS) or ["시장분석"])[0],
                    "cargo":    classify(combined, CARGO_KEYWORDS),
                })
        except Exception as e:
            print(f"[오류] {feed_info['name']}: {e}")
    return articles


def save_to_notion(article):
    today = get_today_str()

    # 한국어 번역
    print(f"  번역 중: {article['title'][:50]}")
    ko_title, ko_summary = translate_to_korean(article["title"], article["summary"])

    props = {
        "제목":     {"title": [{"text": {"content": ko_title}}]},
        "주차":     {"rich_text": [{"text": {"content": today}}]},
        "수집일":   {"date": {"start": today}},
        "출처":     {"rich_text": [{"text": {"content": article["source"]}}]},
        "출처URL":  {"url": article["url"] or None},
        "뉴스요약": {"rich_text": [{"text": {"content": ko_summary}}]},
        "카테고리": {"select": {"name": article["category"]}},
        "발행상태": {"select": {"name": "수집완료"}},
    }
    if article["routes"]:
        props["노선"] = {"multi_select": [{"name": r} for r in article["routes"]]}
    if article["cargo"]:
        props["화물유형"] = {"multi_select": [{"name": c} for c in article["cargo"]]}

    res = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json={"parent": {"database_id": DATABASE_ID}, "properties": props},
    )
    if res.status_code == 200:
        print(f"  ✅ 저장 완료: {ko_title[:50]}")
    else:
        print(f"  ❌ 저장 실패: {res.status_code} / {res.text[:100]}")


def main():
    print(f"\n{'='*55}")
    print(f"수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*55}\n")

    articles = fetch_articles()
    print(f"\n필터링 결과: {len(articles)}건\n")

    for article in articles:
        save_to_notion(article)

    print(f"\n완료! 총 {len(articles)}건 처리")


if __name__ == "__main__":
    main()
