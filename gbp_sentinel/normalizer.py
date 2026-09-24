from __future__ import annotations

import json
import re
import unicodedata
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_POSTAL_RE = re.compile(r"(?<![A-Z0-9])(\d{4})\s*([A-Z]{2})(?![A-Z0-9])", re.IGNORECASE)
_HOUSE_RE = re.compile(
    r"(?<!\w)(\d{1,6})(?:\s*([A-Za-z]{1,4}))?"
    r"(?:\s*[-/]\s*([A-Za-z0-9]{1,8}))?(?!\w)"
)
_PHONE_EXTENSION_RE = re.compile(
    r"(?:ext\.?|extension|toestel|door(?:wahl)?|x)\s*[:.]?\s*\d+\s*$",
    re.IGNORECASE,
)
_TRACKING_QUERY_RE = re.compile(
    r"^(?:utm_[^=]*|gclid|dclid|fbclid|msclkid|gbraid|wbraid|"
    r"_ga|mc_cid|mc_eid|ref|source|campaign)$",
    re.IGNORECASE,
)

_DUTCH_AREA_CODES = {
    "010", "0111", "013", "014", "015", "0161", "0162", "0164", "0165",
    "0166", "0167", "0168", "0172", "0173", "0174", "0175", "0176", "0177",
    "0178", "0180", "0181", "0182", "0183", "0184", "0186", "0187", "020",
    "0222", "0223", "0224", "0226", "0227", "023", "024", "0251", "0252",
    "0255", "026", "0274", "0294", "0297", "0299", "030", "0313", "0314",
    "0315", "0316", "0317", "0318", "0320", "0321", "033", "0341", "0342",
    "0343", "0344", "0345", "0346", "0347", "0348", "035", "036", "038",
    "040", "0411", "0412", "0413", "0416", "0417", "0418", "0419", "0424",
    "046", "0475", "0478", "0481", "0485", "0486", "0487", "0488", "0489",
    "0492", "0493", "0495", "0497", "0499", "050", "0511", "0512", "0513",
    "0514", "0515", "0516", "0517", "0518", "0519", "0521", "0522", "0523",
    "0524", "0525", "0527", "0528", "0529", "053", "0541", "0543", "0544",
    "0545", "0546", "0547", "0548", "055", "0561", "0562", "0566", "0570",
    "0571", "0572", "0573", "0575", "0577", "0578", "058", "0591", "0592",
    "0594", "0595", "0596", "0597", "0598", "0599", "06", "070", "071",
    "072", "073", "074", "075", "076", "077", "078", "079", "085", "088",
}

_MULTI_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "co.nz", "co.za", "com.br", "com.cn", "com.sg", "co.jp", "co.kr",
    "com.mx", "com.tr", "com.ua", "com.pl", "co.in", "com.ar",
}

_LEGAL_SUFFIX_RE = re.compile(
    r"(?:,?\s*(?:b\.?\s*v\.?|bv|v\.?\s*o\.?\s*f\.?|vof|"
    r"coöperatie|cooperatie|eenmanszaak|n\.?\s*v\.?|nv|"
    r"limited|ltd\.?|llc|inc\.?|gmbh))\.?\s*$",
    re.IGNORECASE,
)

_LOCATION_TAGS = {
    "amsterdam", "apeldoorn", "arnhem", "breda", "delft", "den haag",
    "eindhoven", "enschede", "groningen", "haarlem", "hoofddorp",
    "leiden", "maastricht", "nijmegen", "rotterdam", "tilburg", "utrecht",
    "venlo", "zaandam", "zoetermeer", "zwolle",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_phone(raw_phone: str) -> dict[str, Any]:
    raw = _text(raw_phone)
    value = _PHONE_EXTENSION_RE.sub("", raw).strip()
    value = re.sub(r"(?i)(?:tel\.?|phone|mobiel|mobile)\s*[:.]?\s*", "", value)
    compact = re.sub(r"[^\d+]", "", value)

    international = compact.startswith("+")
    if compact.startswith("00"):
        compact = "+" + compact[2:]
        international = True

    national_digits = ""
    e164 = ""

    if compact.startswith("+"):
        country_and_number = re.sub(r"\D", "", compact)
        if country_and_number.startswith("31"):
            national_digits = "0" + country_and_number[2:]
            e164 = "+31" + country_and_number[2:]
        else:
            e164 = "+" + country_and_number if country_and_number else ""
    else:
        digits = re.sub(r"\D", "", compact)
        if digits.startswith("31") and len(digits) >= 10 and not digits.startswith("310"):
            national_digits = "0" + digits[2:]
            e164 = "+31" + digits[2:]
        else:
            national_digits = digits
            if digits.startswith("0") and len(digits) >= 9:
                e164 = "+31" + digits[1:]

    prefix = ""
    if national_digits.startswith("06"):
        prefix = "06"
    elif national_digits.startswith(("085", "088")):
        prefix = national_digits[:3]
    elif national_digits.startswith("0"):
        candidates = sorted(
            (code for code in _DUTCH_AREA_CODES if national_digits.startswith(code)),
            key=len,
            reverse=True,
        )
        prefix = candidates[0] if candidates else national_digits[:3]

    if prefix and len(national_digits) > len(prefix):
        remainder = national_digits[len(prefix):]
        national = f"{prefix}-{remainder}"
    else:
        national = national_digits

    return {
        "raw": raw,
        "e164": e164,
        "national": national,
        "digits": national_digits,
        "is_voip": national_digits.startswith(("085", "088")),
        "is_mobile": national_digits.startswith("06"),
        "area_code": prefix,
        "pbx_prefix_6": national_digits[:6],
    }


def normalize_address(raw_address: str) -> dict[str, Any]:
    raw = _text(raw_address)
    working = re.sub(r"\s+", " ", raw).strip()
    postal_match = _POSTAL_RE.search(working)

    postal_code = ""
    if postal_match:
        postal_code = f"{postal_match.group(1)} {postal_match.group(2).upper()}"
        before = working[:postal_match.start()].strip(" ,;|-")
        after = working[postal_match.end():].strip(" ,;|-")
    else:
        before, after = working, ""

    country = "NL"
    country_match = re.search(
        r"(?:,|\s)\s*(?:the\s+)?(netherlands|nederland|nl)\s*$",
        after or before,
        re.IGNORECASE,
    )
    if country_match:
        country = "NL"
        if after:
            after = after[:country_match.start()].strip(" ,;|-")
        else:
            before = before[:country_match.start()].strip(" ,;|-")

    city = after.strip(" ,;|-")
    street_part = before

    if not postal_match:
        trailing_city = re.search(
            r",\s*([^,]+)$", street_part
        )
        if trailing_city:
            city = trailing_city.group(1).strip()
            street_part = street_part[:trailing_city.start()].strip(" ,;|-")

    house_number = ""
    addition = ""
    house_match = _HOUSE_RE.search(street_part)
    if house_match:
        house_number = house_match.group(1)
        addition = "".join(
            part for part in house_match.groups()[1:] if part
        ).upper()
        street = (
            street_part[:house_match.start()] + street_part[house_match.end():]
        ).strip(" ,;|-")
    else:
        street = street_part.strip(" ,;|-")

    normalized_key = re.sub(
        r"[^a-z0-9]",
        "",
        f"{postal_code}{house_number}{addition}".lower(),
    )

    return {
        "raw": raw,
        "postal_code": postal_code,
        "house_number": house_number,
        "addition": addition,
        "street": street,
        "city": city,
        "country": country,
        "normalized_key": normalized_key,
    }


def normalize_domain(raw_url: str) -> dict[str, Any]:
    raw = _text(raw_url)
    candidate = raw if re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I) else f"https://{raw}"
    parsed = urlsplit(candidate)

    scheme = parsed.scheme.lower() if parsed.scheme.lower() in {"http", "https"} else "https"
    hostname = (parsed.hostname or "").rstrip(".").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        pass

    labels = [label for label in hostname.split(".") if label]
    suffix_length = 2 if ".".join(labels[-2:]) in _MULTI_LABEL_SUFFIXES else 1
    if len(labels) >= suffix_length + 1:
        domain = ".".join(labels[-(suffix_length + 1):])
        subdomain = ".".join(labels[:-(suffix_length + 1)])
    else:
        domain = hostname
        subdomain = ""

    if subdomain == "www":
        subdomain = ""
    elif subdomain.startswith("www."):
        subdomain = subdomain[4:]

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _TRACKING_QUERY_RE.match(key)
    ]
    path = parsed.path or ""
    path = re.sub(r"/+$", "", path)
    canonical_url = urlunsplit(
        (scheme, hostname, path, urlencode(query, doseq=True), "")
    )

    return {
        "raw": raw,
        "canonical_url": canonical_url,
        "domain": domain,
        "subdomain": subdomain,
        "scheme": scheme,
    }


def normalize_business_name(raw_name: str) -> dict[str, Any]:
    raw = _text(raw_name)
    has_delimiters = bool(re.search(r"\||--?|:|/", raw))

    clean_name = unicodedata.normalize("NFKC", raw)
    clean_name = re.sub(r"[|]+", " ", clean_name)
    clean_name = re.sub(r"\s+", " ", clean_name)
    clean_name = clean_name.strip(" \t\r\n,;|:-/")

    brand = _LEGAL_SUFFIX_RE.sub("", clean_name).strip(" \t\r\n,;|:-/")
    brand = re.sub(
        r"\s*[-|,:/]\s*(?:in|te|bij|regio)\s+(.+)$",
        "",
        brand,
        flags=re.IGNORECASE,
    ).strip(" \t\r\n,;|:-/")

    words = re.findall(r"[^\W_]+", clean_name.lower(), flags=re.UNICODE)
    return {
        "raw": raw,
        "clean_name": clean_name,
        "tokens": words,
        "brand_guess": brand,
        "has_delimiters": has_delimiters,
    }


if __name__ == "__main__":
    samples = {
        "addresses": [
            "Hofplein 20, 3032 AC Rotterdam",
            "Stephensonstraat 48, 2561 XW Den Haag",
        ],
        "phones": ["030-1234567", "+31 20 369 1234", "085 060 1234"],
        "domains": ["https://www.Mrdakdekker.nl/contact/?utm_source=gmb"],
    }
    result = {
        "addresses": [normalize_address(value) for value in samples["addresses"]],
        "phones": [normalize_phone(value) for value in samples["phones"]],
        "domains": [normalize_domain(value) for value in samples["domains"]],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
