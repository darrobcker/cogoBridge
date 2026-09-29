"""Before a deal, text may not say who its writer is, or carry anything shaped like a way to reach someone.

This is a seatbelt for an assistant that slips, not a wall: a person who wants to be recognised can
always describe themselves. It looks only at the writer's own name and contact and at generic shapes —
never at who else is a member, so a refusal tells the writer nothing about anybody. It reads text as a
reader would (`as_read`). What it does not catch, on purpose or not yet, is listed in tests/test_guard.py.
"""
from __future__ import annotations

import re
import unicodedata

# Every kind of dash a hyphen: a non-breaking hyphen (which some models write inside numbers) or a typographer's
# dash between the digits hid a phone number that reads the same (audit).
_DASHES = {cp: "-" for cp in (*range(0x2010, 0x2016), 0x2212)}
# Characters that show as nothing but are not formatting characters: a grapheme joiner, variation selectors,
# Hangul fillers and a blank braille cell hid a number just the same (review), and so did the variation
# selectors past U+FE0F and the Mongolian and Khmer ones, which are marks (review).
_BLANK = {0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F, 0x2800, 0x3164, 0xFFA0,
          *range(0xFE00, 0xFE10), *range(0xE0100, 0xE01F0)}


def visible(text: str, invisible: str = "") -> str:
    """Text as a reader sees it: compatibility forms folded (fullwidth digits, @ and brackets), invisible
    characters dropped — a zero-width space inside a number hid it (audit), and between brackets it hid a
    closing fence (review)."""
    text = unicodedata.normalize("NFKC", text or "")
    return "".join(invisible if unicodedata.category(ch) == "Cf" or ord(ch) in _BLANK else ch for ch in text)


def as_read(text: str, invisible: str = "") -> str:
    """As `visible`, and every dash a hyphen."""
    return visible(text, invisible).translate(_DASHES)


# Only from the start of a run: folding can make one character six, and trying every start in the run took
# a third of a second on a 2000-character need (review).
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(r"(?:\b[a-z][a-z0-9+.-]*://|www\.)\S+", re.IGNORECASE)
# A link without a scheme: github.com/x, t.me/x, mayachen.dev all went through (audit). The last label is a
# known top-level domain written in lower case, so node.js/react, ASP.NET/C# and resume.pdf are not links.
# Alone, without a path, only one that is not also a word or a file type, and only written in lower case:
# Booking.com and ASP.net are names (review).
_TLD = ("com|org|net|edu|gov|info|biz|io|co|me|dev|app|ai|gg|gl|gle|ly|tv|fm|to|so|xyz|site|online|link|page|"
        "blog|shop|store|tech|club|live|ee|bio|social|cv|art|design|photo|works|studio|uk|eu|us|de|fr|nl|es|it|pt|pl|se|no|dk|fi|ie|ch|at|be|ca|"
        "au|nz|jp|cn|in|ru|ua|br|mx|ar|za|ng|ke|gh|sg|hk|tr|il")
_BARE_TLD = "com|org|net|edu|gov|info|co|me|dev|app|gg|ly|xyz|social|uk|eu|de|fr|nl|ca|au|nz"
_LABELS = r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
_DOMAIN = re.compile(rf"(?<![\w.-])(?:(?i:{_LABELS})(?:{_TLD})/\S*|{_LABELS}(?:{_BARE_TLD})(?![\w-]))")
# "@6pm" and "meet @the library" are not handles (audit); "@2fast4you" and "@my.kitchen" still are (review).
_HANDLE = re.compile(r"(?<![\w@])@(?!(?:the|a|an|my|our|your|home|work|noon|night)(?![\w.])"
                     r"|\d{1,2}(?:[:.]\d{2})?(?i:am|pm)?(?!\w))\w{2,}")
_PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
# Not a piece of a longer number: one separator looked at let "07700  1996  2006" and "+44 6111 - 1542 - 2093"
# through (review).
_NOT_AFTER_DIGIT = r"(?<!\d[\s.-])(?<!\d[\s.-]{2})(?<!\d[\s.-]{3})"
_UNIT = (r"[$£€¥₹₦₽₺₩₱₫₪₴₵¢]|(?i:\b(?:FCFA|CFA|XOF|XAF|USD|EUR|GBP|NGN|KES|GHS|INR|IDR|Rp|Rs|KSh|rupiah|"
             r"rupees?|naira|francs?|euros?|dollars?|pounds?|shillings?|cedis?|rand|pesos?|reais|rubles?|lira|yen|"
             r"baht|ringgit|km|kg|tonnes?|litres?|liters?|miles?)\b)")
# Numbers that are not phone numbers, blanked before looking for one. Each was refused (simulation, audit):
_NOT_A_PHONE = re.compile(
    # dates, ISO and day- or month-first
    r"\d{4}-\d{2}-\d{2}|\b\d{1,2}(?:\.\d{1,2}\.|-\d{1,2}-|/\d{1,2}/)(?:1[89]|20)\d{2}\b"
    # times, 18:30 and 09.30 — the dotted one never inside a longer run of dotted digits, as 06.12.34.56.78 is
    r"|\d{1,2}:\d{2}|(?<![\d.])(?:[01]?\d|2[0-3])\.[0-5]\d(?!\.?\d)"
    # a span of years ending in two digits, 2019-23 (a span in full is a range, below), and a list of years
    r"|\b(?:19|20)\d{2}\s?-\s?\d{2}\b"
    rf"|{_NOT_AFTER_DIGIT}\b(?:1[89]|20)\d{{2}}(?:(?:\s*[,/&]\s*|\s+(?:and\s+)?)(?:1[89]|20)\d{{2}}\b)+(?![\s.-]{{1,3}}\d)"
    # amounts in thousands, next to a currency or a unit, never a piece of a longer number; bare, 612 345 678
    # is a Spanish mobile
    rf"|(?:{_UNIT})\s?\d{{1,3}}(?:[ .]\d{{3}})+(?![\s.]?\d)"
    rf"|(?<![\d.+]){_NOT_AFTER_DIGIT}(?:\d{{1,3}}(?:[ .]\d{{3}})+\s?-\s?)?\d{{1,3}}(?:[ .]\d{{3}})+\s?(?:{_UNIT})"
    # codes by their label, a grid reference, a coordinate
    r"|(?i:\b(?:ISBN(?:-?1[03])?|ISSN|EAN|UPC|SKU|VIN|serial|frame|grid\s+ref)\b\.?(?:\s*(?:no\.?|number|\#))?)"
    r"\s*:?\s*(?:[A-Z]{2}(?:\s\d{2,5}){1,2}\b|[\dA-Z][\dA-Z-]*)"
    r"|(?<![\d.])-?\d{1,3}\.\d{4,}(?![.\d])")
# A range: a smaller number, a dash, a larger one — 1200-1500, 0700-1900, 45000-55000, 1 200-1 500 — never a piece
# of a longer number. Only one that reads as a range is blanked, since 2123-4567 is a phone number in Hong Kong.
# Thousands grouped with a space or a dot too: folding dashes made "loyer 1 200–1 500" a refusal (review).
_GROUPED = r"\d{3,6}|\d{1,3}(?:[ .]\d{3})+"
_RANGE = re.compile(rf"(?<![\d.,+]){_NOT_AFTER_DIGIT}({_GROUPED})\s?-\s?({_GROUPED})(?![\s.-]{{0,3}}\d)")


def _ranges_out(text: str) -> str:
    def blank(m: re.Match) -> str:
        a, b = (_digits(x) for x in m.groups())
        years = len(a) == len(b) == 4 and 1000 <= int(a) < int(b) <= 2099
        # on the quarter hour, since any HHMM pair let 2123-2345 through (review)
        hours = len(a) == len(b) == 4 and all(int(x[:2]) <= 24 and int(x[2:]) in (0, 15, 30, 45) for x in (a, b))
        round_ = int(a) < int(b) and a.endswith("00") and b.endswith("00") and len(b) - len(a) in (0, 1)
        return " " if years or hours or round_ else m.group()
    return _RANGE.sub(blank, text)


# Reference numbers: a code after a # or glued to letters, or a year and a serial. An ethics approval number,
# "#REK-UiO-2024-00847", was refused twice and the deal waiting on it never happened (simulation). None of them
# may swallow a phone number: the first cut let "WhatsApp #07700900123" and "phone07700900123" through (review).
_REFERENCE = re.compile(r"#[\w-]*\d[\w-]*"
                        r"|\b(?!(?:tel|ph|phone|mob|mobile|cell|call|text|txt|sms|whatsapp|wa|fax|on|me|no|num|number)"
                        r"\W?\d)[^\W\d_]+[-/]?\d[\w/-]*"
                        r"|\b(?:19|20)\d{2}-\d{3,6}\b")


def _references_out(text: str) -> str:
    def keep_or_blank(m: re.Match) -> str:
        code, digits = m.group(), len(_digits(m.group()))
        if digits >= 10 or re.match(r"[\s().-]*\d", text[m.end():]):     # a longer number goes on after it
            return code
        if code.startswith("#") and digits > 8 and not re.search(r"[^\W\d_]", code):
            return code
        return " "
    return _REFERENCE.sub(keep_or_blank, text)


# An organisation is not named by one word of its name: "Kadıköy Street Paws" could not say where the dog
# was, nor a pharmacy the city it dispatches from (simulation). A distinctive word of it with another still is:
# "Leeds leaving-care team" is the Leeds City Council Leaving Care Team. A person with such a word in their name
# — Charlotte Church, Emma Street — is still a person: only a name of three or more words counts (review).
_ORGANISATION = re.compile(r"\b(?:association|bakery|bank|caf[eé]|centre|center|church|club|college|committee|"
                           r"community|company|council|foundation|group|hospital|kitchen|limited|ltd|mosque|"
                           r"network|paws|pharmacy|project|restaurant|school|shop|society|store|street|surgery|"
                           r"synagogue|team|temple|trust|union|university)\b", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


# Words that are names and also something else: Hope, May, Sunday and Grace could not write an ordinary need
# (audit). Each still counts where it reads as a name (review).
_CALENDAR = re.compile(r"(?:mon|tues|wednes|thurs|fri|satur|sun)day|january|february|march|april|may|june|july|"
                       r"august|september|october|november|december", re.IGNORECASE)
_EVERYDAY = re.compile(r"hope|faith|grace|joy|summer|autumn|winter|spring|rose|lily|daisy|dawn|ivy|holly|hazel|ruby|"
                       r"amber|pearl|mark|will|bill|jack|frank|grant|rich|sunny|king|park|hale|young|wood|hill|green|"
                       r"brown|white|black|gr[ae]y|art|pat|sue|rob|don|earl|lee|stone|field|brook|banks|fox|bird|bell|"
                       r"cook|baker|mason|hunter|fisher|miles|guy|page|long|little", re.IGNORECASE)
_TITLES = re.compile(r"mr|mrs|ms|miss|mx|dr|prof|sir|dame|lady|lord|madam|mme|mlle|herr|frau|sra?|aunt(?:ie|y)|uncle|"
                     r"rev|imam|rabbi|pastor|father|sister|brother|doctor|professor|coach|nurse|captain|chef|"
                     r"grandma|granny|nan|nana", re.IGNORECASE)
# Of those, the ones an ordinary sentence opens with: "Hope someone can help", "Will you be around?", "May I ask",
# "Mark my words", "Sunday mornings work best". A given name such as Sue, Jack or Grace opening a sentence is its
# person: exempting every everyday word let "Sue loves gardening" and "Thanks!\nJack" through (review).
_OPENER = re.compile(r"hope|will|mark|hale|summer|autumn|winter|spring|sunny", re.IGNORECASE)
# What makes a word opening a sentence a person even so: anything but a lower-case word or "I" going on along the
# same line — a sign-off, "Sue: ...", "Mark Taylor", "Frank (72)", "Hope's" — or "May x", "Will and I", "Hope and
# Tom", "May lives", "June seeks", "Sunday looking", "Mark also", "Hope used to", "Will moved" (review).
_INTRODUCES = re.compile(r"(?![ \t]+(?:[a-z]|I\b))|[ \t]+(?:and|or)[ \t]+[A-Z]|[ \t]+(?:x+|here|is|was|had|did|"
                         r"would|will|should|must|might|cannot|can|could|from|with|aged|just|also|still|too|looking|"
                         r"seeking|[a-z]*[a-df-z]ed|and[ \t]+(?:me|my|her|his|their)|"
                         r"(?!this\b|(?:morning|afternoon|evening|night)s\b)[a-z]+[a-rt-z]s)\b")
# What puts a weekday or a month in the calendar: a word before it, a day's number or a year beside it, or
# another weekday or month joined to it — "mid-May", "3 May", "May 2027", "Saturday or Sunday" (review). Not a
# greeting's "from" nor "on behalf of": "Love from June" is a sign-off (review).
_DAY = r"(?:3[01]|[12]\d|0?[1-9])(?:st|nd|rd|th)?"
_JOIN = r"(?:[ \t]*[,/&-][ \t]*|[ \t]+(?:or|and|to)[ \t]+)"
_DATE_BEFORE = re.compile(rf"(?:\b(?:on|in|(?<!behalf[ \t])of|by|until|till|next|this|last|every|each|since|early|"
                          r"late|mid|(?<!love[ \t])(?<!wishes[ \t])(?<!regards[ \t])(?<!greetings[ \t])"
                          r"(?<!hugs[ \t])(?<!thanks[ \t])from)"
                          rf"[ \t-]+|(?<!\d){_DAY}[ \t]+|\b(?:{_CALENDAR.pattern}){_JOIN})$", re.IGNORECASE)
_DATE_AFTER = re.compile(rf"[ \t]+(?:{_DAY}|(?:19|20)\d{{2}})\b|{_JOIN}(?:{_CALENDAR.pattern})\b", re.IGNORECASE)
# A word after the name that makes it part of a place's name: Khan Academy, Margaret Street, King's Cross. Not
# Park, Hall or Green, which are as often surnames (review).
_PLACE = re.compile(r"academy|cross|road|avenue|square|station|gardens|library|street", re.IGNORECASE)
# Capitalised in a heading or a sign-off, but no part of a longer name: "Kind Regards Jack", "Posted By Rose" (review).
_NOT_A_NAME = re.compile(r"by|for|from|with|to|all|regards|wishes|thanks|truly|love", re.IGNORECASE)


def _opens_sentence(text: str, i: int) -> bool:
    before = text[:i].rstrip(" \t\"'“‘(*•-")
    return not before or before[-1] in ".!?\n"


def _something_else(text: str, m: re.Match) -> bool:
    """A capitalised word of the name that reads as something else: an ordinary opener going on with an
    ordinary sentence, a date in the calendar, or a word of a place's name — Finsbury Park, King's Cross, Khan
    Academy. Any other capitalised neighbour is a middle name, a title or a heading, and let the name through
    (review)."""
    word, rest = m.group(), text[m.end():m.end() + 64]
    calendar = bool(_CALENDAR.fullmatch(word))
    common = calendar or bool(_EVERYDAY.fullmatch(word))
    # A fixed way back, so the work for each word of the name does not grow with the text before it (review).
    near = text[max(0, m.start() - 64):m.start()]
    if (calendar or _OPENER.fullmatch(word)) and _opens_sentence(text, m.start()) and not _INTRODUCES.match(rest):
        return True
    if calendar and (_DATE_BEFORE.search(near) or _DATE_AFTER.match(rest)):
        return True

    def proper(w: str) -> bool:
        return w[0].isupper() and not _TITLES.fullmatch(w) and not _NOT_A_NAME.fullmatch(w)
    after = re.match(r"(?:['’]s)?[ \t]+([^\W\d_]{2,})", rest)
    if after and proper(after[1]) and _PLACE.fullmatch(after[1]):
        return True
    before = re.search(r"(?<![^\W\d_])([^\W\d_]{2,})[ \t]+$", near)
    return bool(common and before and proper(before[1])
                and not _opens_sentence(text, m.start() - len(near) + before.start(1)))


def _own_name(text: str, name: str) -> str | None:
    words = _WORD.findall(name)
    if not words:
        return None
    # No gap for a middle name here: trying one per word made a crafted name take minutes (review). The single
    # words below already catch "Grace Anne Park".
    whole = re.search(r"(?<!\w)" + r"[\W_]+".join(map(re.escape, words)) + r"(?!\w)", text, re.IGNORECASE)
    if whole:
        return whole.group()
    if _ORGANISATION.search(name) and len([w for w in words if len(w) >= 3]) >= 3:
        present = [m.group() for m in (re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.IGNORECASE)
                                       for w in dict.fromkeys(x.lower() for x in words) if len(w) >= 3) if m]
        distinctive = [p for p in present if p[0].isupper() and not _ORGANISATION.fullmatch(p)]
        return distinctive[0] if len(present) >= 2 and distinctive else None
    for w in dict.fromkeys(words):     # one word of it counts when written the way a name is: capitalised
        if len(w) >= 3:
            for m in re.finditer(rf"(?<!\w){re.escape(w)}(?!\w)", text, re.IGNORECASE):
                if m.group()[0].isupper() and not _something_else(text, m):
                    return m.group()
    return None


def name_words(name: str) -> set[str]:
    """The words of a name as the guard splits it, so "Mary" is a word of Mary-Jane's (review)."""
    return {w.lower() for w in _WORD.findall(as_read(name))}


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def identifies(text: str, name: str = "", contact: str = "") -> str | None:
    """The part of `text`, as a reader sees it, that must come out, or None."""
    read, name, contact = as_read(text), as_read(name), as_read(contact).strip()
    # An invisible character between the words of the name reads as nothing, or as a space.
    hit = _own_name(read, name) or _own_name(as_read(text, " "), name)
    if hit:
        return hit
    # Matched whole: a contact set to a short word refused every message containing its letters.
    if contact and re.search(rf"(?<!\w){re.escape(contact)}(?!\w)", read, re.IGNORECASE):
        return contact
    for shape in (_EMAIL, _LINK, _DOMAIN, _HANDLE):
        m = shape.search(read)
        if m:
            return m.group()
    for m in _PHONE.finditer(_references_out(_ranges_out(_NOT_A_PHONE.sub(" ", read)))):
        if len(_digits(m.group())) >= 8:
            return m.group().strip()
    return None
