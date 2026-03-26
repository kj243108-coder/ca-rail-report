import os
import re
import feedparser
import requests
from datetime import datetime, timezone
from deep_translator import GoogleTranslator

NOTION_TOKEN    = os.getenv("NOTION_TOKEN")
DATABASE_ID     = os.getenv("NOTION_DATABASE_ID")

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

# 중앙아시아 필수 키워드 - 반드시 하나 이상 포함돼야 수집
CENTRAL_ASIA_REQUIRED = [
    "kazakhstan", "kazakh", "ktz",
    "uzbekistan", "uzbek",
    "kyrgyzstan", "kyrgyz",
    "turkmenistan", "turkmen",
    "tajikistan", "tajik",
    "central asia",
    "silk road", "middle corridor", "trans-caspian",
    "belt and road", "bri",
    "china-europe rail", "china europe rail",
    "eurasian corridor", "titr",
]

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


def get_week_str():
    return datetime.now(timezone.utc).strftime("%Y-W%W")


def classify(text, keyword_map):
    text_lower = text.lower()
    return [tag for tag, kws in keyword_map.items() if any(k in text_lower for k in kws)]


def is_central_asia_related(text):
    text_lower = text.lower()
    return any(kw in text_lower for kw in CENTRAL_ASIA_REQUIRED)


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text).strip()


def is_duplicate(url):
    """Notion DB에 동일 URL이 있으면 True 반환"""
    if not url:
        return False
    try:
        res = requests.post(
            f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "property": "출처URL",
                    "url": {"equals": url}
                }
            },
            timeout=10,
        )
        if res.status_code == 200:
            return len(res.json().get("results", [])) > 0
    except Exception as e:
        print(f"  ⚠️ 중복 확인 실패: {e}")
    return False


def translate_to_korean(title, summary):
    """Google 번역 (무료, API 키 불필요)"""
    try:
        translator = GoogleTranslator(source='auto', target='ko')
        ko_title   = translator.translate(title) or title
        ko_summary = translator.translate(summary[:500]) if summary else ""
        print(f"  ✅ 번역 완료: {ko_title[:40]}")
        return ko_title, ko_summary
    except Exception as e:
        print(f"  ⚠️ 번역 실패 (원문 사용): {e}")
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
    today    = get_today_str()
    week_str = get_week_str()

    # 중복 확인
    if is_duplicate(article["url"]):
        print(f"  ⏭️ 중복 건너뜀: {article['title'][:50]}")
        return

    # 한국어 번역
    print(f"  번역 중: {article['title'][:50]}")
    ko_title, ko_summary = translate_to_korean(article["title"], article["summary"])

    props = {
        "제목":     {"title": [{"text": {"content": ko_title}}]},
        "주차":     {"rich_text": [{"text": {"content": week_str}}]},
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
