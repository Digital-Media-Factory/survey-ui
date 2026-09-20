"""Turns a raw Google Forms response sheet into chartable statistics.

Nothing here is hard-coded to the Arabic child-safety survey: column roles are
inferred, so a new form export with different questions still works.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd

# ---------------------------------------------------------------- cleaning ---

# Free-text country answers arrive misspelled, in multiple languages (English, French, Arabic),
# and sometimes include cities or phrases. Normalising them unifies duplicates into standard Arabic names.
COUNTRY_ALIASES: dict[str, str] = {
    # المغرب
    "morocco": "المغرب",
    "maroc": "المغرب",
    "le maroc": "المغرب",
    "morocco,casablanca": "المغرب",
    "casablanca": "المغرب",
    "rabat": "المغرب",
    "marrakech": "المغرب",
    "tangier": "المغرب",
    "المغرب": "المغرب",
    "المغرب ": "المغرب",
    # موريتانيا
    "mauritania": "موريتانيا",
    "nouakchott": "موريتانيا",
    "موريتانيا": "موريتانيا",
    "موريتانيا ": "موريتانيا",
    # الأردن
    "jordan": "الأردن",
    "amman": "الأردن",
    "الاردن": "الأردن",
    "الأردن": "الأردن",
    "المملكة الاردنية الهاشمية": "الأردن",
    "المملكة الأردنية الهاشمية": "الأردن",
    # مصر
    "egypt": "مصر",
    "cairo": "مصر",
    "alexandria": "مصر",
    "giza": "مصر",
    "مصر": "مصر",
    "القاهره": "مصر",
    "القاهرة": "مصر",
    # اليمن
    "yemen": "اليمن",
    "yemen ": "اليمن",
    "sanaa": "اليمن",
    "aden": "اليمن",
    "اليمن": "اليمن",
    "اليمن ": "اليمن",
    # العراق
    "iraq": "العراق",
    "baghdad": "العراق",
    "erbil": "العراق",
    "basra": "العراق",
    "mosul": "العراق",
    "العراق": "العراق",
    "في العراق": "العراق",
    # لبنان
    "lebanon": "لبنان",
    "beirut": "لبنان",
    "لبنان": "لبنان",
    "لبنان ": "لبنان",
    "بيروت": "لبنان",
    # سوريا
    "syria": "سوريا",
    "damascus": "سوريا",
    "aleppo": "سوريا",
    "سوريا": "سوريا",
    "سورية": "سوريا",
    # فلسطين
    "palestine": "فلسطين",
    "jerusalem": "فلسطين",
    "gaza": "فلسطين",
    "ramallah": "فلسطين",
    "فلسطين": "فلسطين",
    # ليبيا
    "libya": "ليبيا",
    "tripoli": "ليبيا",
    "benghazi": "ليبيا",
    "ليبيا": "ليبيا",
    # السودان
    "sudan": "السودان",
    "khartoum": "السودان",
    "السودان": "السودان",
    # السعودية
    "saudi": "السعودية",
    "saudi arabia": "السعودية",
    "ksa": "السعودية",
    "riyadh": "السعودية",
    "jeddah": "السعودية",
    "mecca": "السعودية",
    "medina": "السعودية",
    "dammam": "السعودية",
    "السعودية": "السعودية",
    "المملكة العربية السعودية": "السعودية",
    # الإمارات
    "united arab emirates": "الإمارات",
    "uae": "الإمارات",
    "dubai": "الإمارات",
    "abu dhabi": "الإمارات",
    "sharjah": "الإمارات",
    "الإمارات": "الإمارات",
    "الامارات": "الإمارات",
    # الجزائر
    "algeria": "الجزائر",
    "algiers": "الجزائر",
    "oran": "الجزائر",
    "الجزائر": "الجزائر",
    # تونس
    "tunisia": "تونس",
    "tunis": "تونس",
    "sfax": "تونس",
    "تونس": "تونس",
    # الكويت
    "kuwait": "الكويت",
    "kuwait city": "الكويت",
    "الكويت": "الكويت",
    # قطر
    "qatar": "قطر",
    "doha": "قطر",
    "قطر": "قطر",
    # البحرين
    "bahrain": "البحرين",
    "manama": "البحرين",
    "البحرين": "البحرين",
    # عمان
    "oman": "سلطنة عمان",
    "muscat": "سلطنة عمان",
    "salalah": "سلطنة عمان",
    "سلطنة عمان": "سلطنة عمان",
    # الصومال
    "somalia": "الصومال",
    "mogadishu": "الصومال",
    "الصومال": "الصومال",
    # جيبوتي
    "djibouti": "جيبوتي",
    "جيبوتي": "جيبوتي",
    # جزر القمر
    "comoros": "جزر القمر",
    "جزر القمر": "جزر القمر",
    # دول عالمية
    "turkey": "تركيا", "turkiye": "تركيا", "istanbul": "تركيا", "ankara": "تركيا",
    "united states": "الولايات المتحدة", "usa": "الولايات المتحدة", "united states of america": "الولايات المتحدة", "us": "الولايات المتحدة",
    "united kingdom": "المملكة المتحدة", "uk": "المملكة المتحدة", "britain": "المملكة المتحدة", "england": "المملكة المتحدة", "great britain": "المملكة المتحدة", "london": "المملكة المتحدة",
    "germany": "ألمانيا", "deutschland": "ألمانيا", "berlin": "ألمانيا",
    "france": "فرنسا", "paris": "فرنسا",
    "italy": "إيطاليا", "italia": "إيطاليا", "rome": "إيطاليا",
    "spain": "إسبانيا", "espana": "إسبانيا", "madrid": "إسبانيا", "barcelona": "إسبانيا",
    "canada": "كندا", "toronto": "كندا", "montreal": "كندا",
    "australia": "أستراليا", "sydney": "أستراليا",
    "russia": "روسيا", "moscow": "روسيا",
    "china": "الصين", "beijing": "الصين",
    "japan": "اليابان", "tokyo": "اليابان",
    "south korea": "كوريا الجنوبية", "korea": "كوريا الجنوبية", "seoul": "كوريا الجنوبية",
    "india": "الهند", "new delhi": "الهند",
    "pakistan": "باكستان", "islamabad": "باكستان",
    "indonesia": "إندونيسيا", "jakarta": "إندونيسيا",
    "malaysia": "ماليزيا", "kuala lumpur": "ماليزيا",
    "netherlands": "هولندا", "holland": "هولندا", "amsterdam": "هولندا",
    "belgium": "بلجيكا", "brussels": "بلجيكا",
    "switzerland": "سويسرا", "suisse": "سويسرا",
    "sweden": "السويد", "stockholm": "السويد",
    "norway": "النرويج", "oslo": "النرويج",
    "denmark": "الدنمارك", "copenhagen": "الدنمارك",
    "finland": "فنلندا", "helsinki": "فنلندا",
    "austria": "النمسا", "vienna": "النمسا",
    "greece": "اليونان", "athens": "اليونان",
    "portugal": "البرتغال", "lisbon": "البرتغال",
    "ireland": "أيرلندا", "dublin": "أيرلندا",
    "poland": "بولندا", "warsaw": "بولندا",
    "ukraine": "أوكرانيا", "kyiv": "أوكرانيا",
    "brazil": "البرازيل", "brasil": "البرازيل",
    "argentina": "الأرجنتين",
}

COUNTRY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"moroc|maroc|مغرب|casablanca|rabat|الدار البيضاء|كازا|طنجة|tanger|tangier|مراكش|فاس|agadir", re.I), "المغرب"),

    (re.compile(r"mauritani|موريتان|نواكشوط|nouakchott", re.I), "موريتانيا"),
    (re.compile(r"jordan|أردن|اردن|amman|عمان|عمّان", re.I), "الأردن"),
    (re.compile(r"yemen|يمن|صنعاء|عدن|sanaa|aden", re.I), "اليمن"),
    (re.compile(r"egypt|مصر|قاهر|cairo|alexandria|اسكندر|جيزة|giza|منصورة|طنطا", re.I), "مصر"),
    (re.compile(r"palestin|فلسطين|غزة|gaza|قدس|jerusalem|رام الله|ramallah|نابلس|خليل|جنين", re.I), "فلسطين"),
    (re.compile(r"syria|سوريا|سورية|دمشق|damascus|حلب|aleppo|حمص|شام", re.I), "سوريا"),
    (re.compile(r"leban|لبنان|بيروت|beirut|صيدا|sidon", re.I), "لبنان"),
    (re.compile(r"iraq|عراق|بغداد|baghdad|بصرة|basra|اربيل|erbil|أربيل|موصل|mosul", re.I), "العراق"),
    (re.compile(r"liby|ليبيا|طرابلس|tripoli|بنغازي|benghazi|مصراتة", re.I), "ليبيا"),
    (re.compile(r"sudan|سودان|خرطوم|khartoum|أم درمان", re.I), "السودان"),
    (re.compile(r"saudi|ksa|سعودي|رياض|riyadh|جدة|jeddah|مكة|mecca|مدينة منورة|medina|دمام|dammam", re.I), "السعودية"),
    (re.compile(r"alger|جزائر|وهران|oran|قسنطينة|constantine", re.I), "الجزائر"),
    (re.compile(r"tunis|تونس|صفاقس|sfax|سوسة|sousse", re.I), "تونس"),
    (re.compile(r"emirates|uae|إمارات|امارات|دبي|dubai|أبوظبي|ابوظبي|abu dhabi|شارقة|sharjah|عجمان", re.I), "الإمارات"),
    (re.compile(r"kuwait|كويت", re.I), "الكويت"),
    (re.compile(r"qatar|قطر|دوحة|doha", re.I), "قطر"),
    (re.compile(r"bahrain|بحرين|منامة|manama", re.I), "البحرين"),
    (re.compile(r"oman|سلطنة عمان|مسقط|muscat|صلالة|salalah", re.I), "سلطنة عمان"),
    (re.compile(r"somali|صومال|مقديشو|mogadishu", re.I), "الصومال"),
    (re.compile(r"djibouti|جيبوتي", re.I), "جيبوتي"),
    (re.compile(r"comoros|جزر القمر", re.I), "جزر القمر"),
    (re.compile(r"turkey|türkiye|تركيا|إسطنبول|istanbul|اسطنبول|أنقرة|ankara", re.I), "تركيا"),
    (re.compile(r"germany|deutschland|ألمانيا|المانيا|برلين|berlin", re.I), "ألمانيا"),
    (re.compile(r"france|فرنسا|باريس|paris", re.I), "فرنسا"),
    (re.compile(r"uk|britain|england|great britain|بريطانيا|إنجلترا|انجلترا|لندن|london", re.I), "بريطانيا"),
    (re.compile(r"united states|usa|أمريكا|امريكا|واشنطن|washington", re.I), "الولايات المتحدة"),
    (re.compile(r"canada|كندا|toronto|montreal", re.I), "كندا"),
    (re.compile(r"australia|أستراليا|استراليا|sydney", re.I), "أستراليا"),
    (re.compile(r"russia|روسيا|moscow", re.I), "روسيا"),
    (re.compile(r"china|الصين|beijing", re.I), "الصين"),
    (re.compile(r"japan|اليابان|tokyo", re.I), "اليابان"),
    (re.compile(r"korea|كوريا|seoul", re.I), "كوريا الجنوبية"),
    (re.compile(r"india|الهند|delhi", re.I), "الهند"),
    (re.compile(r"pakistan|باكستان|islamabad", re.I), "باكستان"),
    (re.compile(r"indonesia|إندونيسيا|اندونيسيا|jakarta", re.I), "إندونيسيا"),
    (re.compile(r"malaysia|ماليزيا|kuala lumpur", re.I), "ماليزيا"),
    (re.compile(r"netherlands|holland|هولندا|amsterdam", re.I), "هولندا"),
    (re.compile(r"belgium|بلجيكا|brussels", re.I), "بلجيكا"),
    (re.compile(r"switzerland|suisse|schweiz|سويسرا", re.I), "سويسرا"),
    (re.compile(r"sweden|سويد|السويد|stockholm", re.I), "السويد"),
    (re.compile(r"norway|النرويج|oslo", re.I), "النرويج"),
    (re.compile(r"denmark|الدنمارك|copenhagen", re.I), "الدنمارك"),
    (re.compile(r"finland|فنلندا|helsinki", re.I), "فنلندا"),
    (re.compile(r"austria|النمسا|vienna", re.I), "النمسا"),
    (re.compile(r"greece|اليونان|athens", re.I), "اليونان"),
    (re.compile(r"portugal|البرتغال|lisbon", re.I), "البرتغال"),
    (re.compile(r"ireland|أيرلندا|ايرلندا|dublin", re.I), "أيرلندا"),
    (re.compile(r"poland|بولندا|warsaw", re.I), "بولندا"),
    (re.compile(r"ukraine|أوكرانيا|اوكرانيا|kyiv", re.I), "أوكرانيا"),
    (re.compile(r"brazil|brasil|البرازيل", re.I), "البرازيل"),
    (re.compile(r"argentina|الأرجنتين|الارجنتين", re.I), "الأرجنتين"),
    (re.compile(r"south africa|جنوب أفريقيا|جنوب افريقيا", re.I), "جنوب أفريقيا"),
]



ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0640]")

# Words too common to be interesting in an Arabic keyword count.
STOPWORDS = {
    "في", "من", "على", "عن", "الى", "إلى", "مع", "أن", "ان", "هذا", "هذه",
    "التي", "الذي", "ما", "لا", "هو", "هي", "كل", "أو", "او", "ثم", "قد",
    "يجب", "كان", "لكن", "بعض", "عند", "به", "لهم", "لها", "انا", "أنا",
    "و", "يا", "كما", "بين", "حتى", "اي", "أي", "هم", "نحن", "بشكل", "غير",
}


def tidy(value: Any) -> str:
    """Display form: trimmed only. Tashkeel and spelling stay exactly as written."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).replace("\u200f", "").replace("\u200e", "")
    return re.sub(r"\s+", " ", s).strip()


def normalize_text(value: Any) -> str:
    """Matching form: also folds hamza variants, so أحياناً == احيانا.

    Only ever used as a grouping key or for search — never shown to the user,
    because folding hamza produces misspelled Arabic on screen.
    """
    s = ARABIC_DIACRITICS.sub("", tidy(value))
    return s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")


def canonical_country(value: Any) -> str:
    cleaned = tidy(value)
    if not cleaned:
        return "غير محدد"

    # 1. Exact / alias lookup
    key = normalize_text(cleaned).lower()
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]

    # 2. Pattern matching for multilingual variations (Morocco, Casablanca, Le Maroc, etc.)
    for pattern, canonical_name in COUNTRY_PATTERNS:
        if pattern.search(cleaned):
            return canonical_name

    return cleaned



# ------------------------------------------------------------ question type ---

MULTI_HINTS = ("يمكنك الاختيار", "اختر كل", "select all", "up to 3", "حتى 3")
LONG_ANSWER_CHARS = 45


def classify(series: pd.Series, header: str, n_rows: int) -> str:
    """single | multi | open | timestamp"""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "timestamp"

    values = [normalize_text(v) for v in series.dropna()]
    values = [v for v in values if v]
    if not values:
        return "open"

    uniq = len(set(values))
    ratio = uniq / max(len(values), 1)
    avg_len = sum(len(v) for v in values) / len(values)
    comma_share = sum(1 for v in values if "," in v) / len(values)

    if any(h in header for h in MULTI_HINTS) or comma_share >= 0.3:
        return "multi"
    # Free text: nearly every answer unique AND answers are sentence-length.
    if ratio > 0.8 and avg_len > LONG_ANSWER_CHARS:
        return "open"
    if uniq > max(12, n_rows * 0.7) and avg_len > 25:
        return "open"
    return "single"


def split_multi(value: str) -> list[str]:
    parts = re.split(r"[,،;؛]\s*", value)
    return [p.strip() for p in parts if p.strip()]


# ----------------------------------------------------------------- dataset ---


class SurveyData:
    """Holds one loaded sheet plus its derived schema."""

    def __init__(self, df: pd.DataFrame, source: str = "unknown"):
        df = df.dropna(how="all").copy()
        df.columns = [str(c).strip() for c in df.columns]
        self.source = source
        self.df = df
        self.n = len(df)
        self.questions: list[dict[str, Any]] = []

        for col in df.columns:
            qtype = classify(df[col], col, self.n)
            self.questions.append(
                {"id": self._slug(col), "title": col, "type": qtype}
            )

        self.by_id = {q["id"]: q for q in self.questions}
        self.timestamp_col = next(
            (q["title"] for q in self.questions if q["type"] == "timestamp"), None
        )
        self._clean()
        self.filter_cols = self._pick_filters()


    # -- setup ---------------------------------------------------------------

    @staticmethod
    def _slug(col: str) -> str:
        return "q" + str(abs(hash(col)) % (10**10))

    def _pick_filters(self) -> list[str]:
        """Single-choice questions with a handful of options make good filters."""
        out = []
        for q in self.questions:
            if q["type"] != "single":
                continue
            nun = self.df[q["title"]].nunique(dropna=True)
            if 2 <= nun <= 10:
                out.append(q["title"])
        return out[:6]

    def _clean(self):
        for q in self.questions:
            col = q["title"]
            if q["type"] == "timestamp":
                continue
            if "دولة" in col or "country" in col.lower():
                self.df[col] = self.df[col].map(canonical_country)
                q["cleaned"] = True
            elif q["type"] in ("single", "multi"):
                self.df[col] = self.df[col].map(lambda v: tidy(v) or "بدون إجابة")

    # -- querying ------------------------------------------------------------

    def filtered(self, filters: dict[str, list[str]]) -> pd.DataFrame:
        df = self.df
        for col, wanted in filters.items():
            if col in df.columns and wanted:
                keys = {normalize_text(w) for w in wanted}
                df = df[df[col].map(lambda v: normalize_text(v) in keys)]
        return df

    def distribution(self, col: str, qtype: str, df: pd.DataFrame) -> list[dict]:
        """Count by normalised key, label with the most common original spelling."""
        if qtype == "multi":
            values = [
                part for v in df[col].dropna() for part in split_multi(str(v))
            ]
        else:
            values = [str(v) for v in df[col].dropna() if str(v).strip()]

        counter: Counter[str] = Counter()
        spellings: dict[str, Counter[str]] = {}
        for raw in values:
            key = normalize_text(raw)
            if not key:
                continue
            counter[key] += 1
            spellings.setdefault(key, Counter())[tidy(raw)] += 1

        total = sum(counter.values()) or 1
        return [
            {
                "label": spellings[key].most_common(1)[0][0],
                "count": c,
                "percent": round(c * 100 / total, 1),
            }
            for key, c in counter.most_common()
        ]

    def open_answers(self, col: str, df: pd.DataFrame) -> list[str]:
        return [
            str(v).strip()
            for v in df[col].dropna()
            if str(v).strip() and len(str(v).strip()) > 1
        ]

    def keywords(self, col: str, df: pd.DataFrame, top: int = 18) -> list[dict]:
        counter: Counter[str] = Counter()
        for text in self.open_answers(col, df):
            for word in re.findall(r"[\w\u0600-\u06FF]+", normalize_text(text)):
                if len(word) > 2 and word not in STOPWORDS:
                    counter[word] += 1
        return [{"word": w, "count": c} for w, c in counter.most_common(top)]

    # -- payloads ------------------------------------------------------------

    def meta(self) -> dict:
        return {
            "source": self.source,
            "responses": self.n,
            "questions": len(self.questions),
            "timestampColumn": self.timestamp_col,
            "dateRange": (
                [
                    str(self.df[self.timestamp_col].min())[:10],
                    str(self.df[self.timestamp_col].max())[:10],
                ]
                if self.timestamp_col
                else None
            ),
            "filters": [
                {
                    "column": c,
                    "options": sorted(
                        {str(v) for v in self.df[c].dropna() if str(v).strip()}
                    ),
                }
                for c in self.filter_cols
            ],
            "schema": [
                {"id": q["id"], "title": q["title"], "type": q["type"]}
                for q in self.questions
            ],
        }

    def stats(self, filters: dict[str, list[str]]) -> dict:
        df = self.filtered(filters)
        blocks = []
        for q in self.questions:
            col, qtype = q["title"], q["type"]
            if qtype == "timestamp":
                continue
            if qtype == "open":
                blocks.append(
                    {
                        "id": q["id"],
                        "title": col,
                        "type": "open",
                        "answered": len(self.open_answers(col, df)),
                        "answers": self.open_answers(col, df),
                        "keywords": self.keywords(col, df),
                    }
                )
                continue
            dist = self.distribution(col, qtype, df)
            blocks.append(
                {
                    "id": q["id"],
                    "title": col,
                    "type": qtype,
                    "answered": int(df[col].notna().sum()),
                    "options": len(dist),
                    "chart": "doughnut" if qtype == "single" and len(dist) <= 5 else "bar",
                    "data": dist,
                }
            )
        return {"matched": len(df), "total": self.n, "blocks": blocks}

    def kpis(self, filters: dict[str, list[str]]) -> list[dict]:
        df = self.filtered(filters)
        out = [{"label": "عدد المشاركين", "value": len(df), "hint": f"من أصل {self.n}"}]

        def share(col_match: str, wanted: tuple[str, ...], label: str) -> None:
            col = next((c for c in df.columns if normalize_text(col_match) in normalize_text(c)), None)
            if col is None or df.empty:
                return
            terms = [normalize_text(w) for w in wanted]
            hits = df[col].astype(str).map(
                lambda v: any(w in normalize_text(v) for w in terms)
            ).sum()
            out.append(
                {
                    "label": label,
                    "value": f"{round(hits * 100 / len(df))}%",
                    "hint": f"{int(hits)} مشارك",
                }
            )

        share("كم مرة تستخدم الإنترنت", ("يومي",), "يستخدمون الإنترنت يومياً")
        share("هل تستخدم أدوات للذكاء الاصطناعي", ("أحيان", "كثير"), "يستخدمون الذكاء الاصطناعي")
        share("هل تعرف ماذا تفعل", ("نعم",), "يعرفون بمن يستعينون")
        share("يستمعون بما يكفي", ("لا", "لا أعرف"), "لا يشعرون أن صوتهم مسموع")
        return out[:5]

    def highlights(self, filters: dict[str, list[str]], top: int = 6) -> list[dict]:
        """The single most common answer for each closed question, strongest first."""
        df = self.filtered(filters)
        out = []
        for q in self.questions:
            if q["type"] not in ("single", "multi"):
                continue
            dist = self.distribution(q["title"], q["type"], df)
            if not dist or len(dist) < 2:
                continue
            best = dist[0]
            out.append(
                {
                    "question": q["title"],
                    "label": best["label"],
                    "count": best["count"],
                    "percent": best["percent"],
                }
            )
        out.sort(key=lambda h: h["percent"], reverse=True)
        return out[:top]

    def rows(self, filters: dict[str, list[str]], search: str = "") -> list[dict]:
        df = self.filtered(filters)
        if search:
            needle = normalize_text(search)
            mask = df.apply(
                lambda r: needle in normalize_text(" ".join(map(str, r.values))), axis=1
            )
            df = df[mask]
        out = df.copy()
        if self.timestamp_col and self.timestamp_col in out:
            out[self.timestamp_col] = out[self.timestamp_col].astype(str)
        return out.fillna("").astype(str).to_dict(orient="records")
