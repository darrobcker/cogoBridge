"""The text guard: the writer's own identity, and anything shaped like a way to reach someone."""
from __future__ import annotations

import time

import pytest

from bridge import guard

ME = dict(name="Maya Chen", contact="maya.chen.dev@example.com")


@pytest.mark.parametrize("text", [
    "my person is Maya Chen", "MAYA  CHEN here", "ask for Maya", "Chen would love this",
    "write to maya.chen.dev@example.com", "anyone@else.org works too", "call +44 7700 900123",
    "415 555 0142 after six", "find me at @mayabuilds", "see https://github.com/maya/receipts",
    "details on www.example.com"])
def test_refused(text):
    assert guard.identifies(text, **ME)


@pytest.mark.parametrize("text", [
    "I'm a frontend dev looking for a backend partner", "Tuesday 2026-09-23 at 18:30 works",
    "between 2024 and 2026 I built three apps", "V3-V4 climber, 5 years, free after 6:30pm",
    "message me on Instagram later", "email me once we've both said yes", "room 1204, floor 12",
    "she may chen-ge her mind",
    # spans of years were refused as phone numbers (simulation)
    "bound journals (1975-2010), free", "notebooks from 1958 – 1975", "worked there 2019-23",
    # an ethics approval number was refused twice as a phone number, and the deal waiting on it never
    # happened (simulation)
    "approved under #REK-UiO-2024-00847", "case 2024-00847 at the tribunal", "order #12345678",
    "planning application 2023/01142/FUL", "invoice INV-20240917"])
def test_allowed(text):
    assert guard.identifies(text, **ME) is None


def test_a_word_of_the_name_counts_only_when_written_as_a_name():
    assert guard.identifies("ask Will, my person will be around", name="Will Young") == "Will"
    assert guard.identifies("my person will be around, and is young at heart", name="Will Young") is None


def test_nothing_set_up_yet_still_catches_shapes():
    assert guard.identifies("ping me: a@b.co") and guard.identifies("a climbing partner") is None


@pytest.mark.parametrize("name, text", [
    # A place in an organisation's own name was refused as naming itself, and the life-critical reply
    # waiting on it cost a round trip (simulation, twice)
    ("Kadıköy Street Paws", "a dog seen near the ferry in Kadıköy"),
    ("Central Hospital Pharmacy, Antananarivo", "we dispatch from Antananarivo within the hour"),
    ("Kings Heath Community Kitchen", "surplus bread wanted, we collect in Kings Norton"),
    ("Northfield Food Bank", "Saturday sorting volunteers wanted in Northfield")])
def test_one_word_of_an_organisations_name_is_not_its_name(name, text):
    assert guard.identifies(text, name=name) is None
    assert guard.identifies(f"this is {name}", name=name)
    assert guard.identifies(f"{name.split()[0]} {name.split()[-1].lower()} here", name=name)


@pytest.mark.parametrize("text", ["+44 7700 900123", "07700 900123", "(415) 555-0142", "0161 496 0000",
                                  "call 2025550147",
                                  "tel-07700900123", "whatsapp/07700900123",
                                  # the reference-number exemption let these through (review)
                                  "WhatsApp #07700900123", "WA:#07700 900123", "Ring #0161 496 0000", "#447700900123",
                                  "call me on07700900123", "phone07700900123", "tel07700900123",
                                  "whatsapp07700900123", "wa.me/447700900123", "me/0161-496-0000",
                                  "call 2012-345678 after 6"])
def test_phone_numbers_are_still_phone_numbers(text):
    assert guard.identifies(text)


@pytest.mark.parametrize("name, text", [
    # an organisation word in a person's surname, or a long personal name, let their first name through (review)
    ("Charlotte Church", "Charlotte here"), ("Emma Street", "Emma here"), ("Shirley Temple", "Shirley here"),
    ("Tom Bank", "Tom here, keen"), ("Omar's Bakery", "Omar here"),
    ("María José García López de la Vega", "soy María"), ("Mohammed bin Rashid Al Maktoum", "Mohammed here")])
def test_a_persons_first_name_is_still_their_name(name, text):
    assert guard.identifies(text, name=name)


@pytest.mark.parametrize("name, text", [
    ("Northfield Food Bank", "we are a food bank, open Saturdays"),
    ("Kings Heath Community Kitchen", "our community kitchen serves 60"),
    ("Leeds Rugby Club", "our rugby club needs a coach")])
def test_an_organisation_may_say_what_it_is(name, text):
    """It was refused for "food bank" and "community kitchen" (review)."""
    assert guard.identifies(text, name=name) is None


# -- the audit's guard findings: each string is one the running code got wrong ---------------------------

@pytest.mark.parametrize("text", [
    "portfolio: mayachen.dev", "code's on github.com/mayabuilds", "book a slot at calendly.com/maya-c",
    "join t.me/+AbCdEf12", "chat at wa.me/message/ABC123", "profile: linkedin.com/in/mchen",
    "see instagram.com/mayabuilds", "discord.gg/abcdef", "forms.gle/xyz123", "meet.google.com/abc-defg-hij",
    "maps.app.goo.gl/AbCdE", "paypal.me/mayac", "bit.ly/3xYz", "GitHub.com/maya",
    # the first fix still let the personal-page kind through (review)
    "linktr.ee/mayac", "lnk.bio/maya", "maya.bsky.social", "portfolio: mayachen.me", "read.cv/maya",
    "mayachen.design/x", "mayachen.photo/x", "mayachen.works/x", "mayachen.studio/x", "mayachen.art/x",
    "tg://resolve?domain=mayabuilds"])
def test_a_link_without_https_or_www_is_a_link(text):
    """Only links starting https:// or www. were caught, so the way people and assistants usually write one —
    github.com/x, mayachen.dev — went through before any deal (audit)."""
    assert guard.identifies(text, **ME)


@pytest.mark.parametrize("text", [
    "node.js/react developer wanted", "Next.js or Vue.js, either", "ASP.NET/C# help", "my resume.pdf is ready",
    "e.g. a 3.5/5 rating", "i.e. soon", "U.K./Europe only", "a.m./p.m. both fine", "I use claude.ai and socket.io",
    # a brand named by its domain, written as a name, was refused by the first fix (review)
    "it's cheaper than on Booking.com", "bought it on Amazon.co.uk", "anyone with an Ancestry.com subscription?",
    "selling on eBay.de", "ADO.net or ASP.net developer"])
def test_a_dotted_word_is_not_a_link(text):
    assert guard.identifies(text, **ME) is None


@pytest.mark.parametrize("text", [
    "+44‑7700‑900123", "0161–496–0000", "0161—496—0000", "(0161)‒496‒0000",
    "07700‐900123", "07700⁠900123", "phone 07700​900123", "07700−900123",
    "０７７００ ９００１２３", "mayac＠example.com", "0161―496―0000",
    # characters that show as nothing but are not formatting characters still hid a number (review)
    "text 07700\u034f900123", "text 07700\ufe0f900123", "text 07700\u3164900123", "text 07700\u2800900123",
    "text 07700\u115f900123", "text 07700\uffa0900123",
    # nor a variation selector past U+FE0F, or a Mongolian or Khmer one: marks, not formatting (review)
    "call 0\U000e01007700 9\U000e010012345", "text 07700\u180b900123", "text 07700\u17b4900123"])
def test_a_contact_is_read_as_a_reader_reads_it(text):
    """A non-breaking hyphen, a typographer's dash or an invisible character between the digits broke the phone
    shape, though the number reads the same (audit); a fullwidth @ did the same to an email (audit, #69)."""
    assert guard.identifies(text, **ME)


def test_an_invisible_character_does_not_hide_the_name():
    assert guard.identifies("my person is Ma​ya Chen", **ME)
    assert guard.identifies("my person is Maya​Chen", **ME)
    assert guard.identifies("my person is Maya­Chen", **ME)


@pytest.mark.parametrize("text", [
    "am 23.09.2026 um 18 Uhr", "vom 01.10.2026 bis 31.12.2026", "23-09-2026 pickup", "from 01.10.2026",
    "on 09/23/2026 or 23/09/2026",
    "budget £1500-2000 for a used car", "rent 1200-1500 a month", "salary 45000-55000",
    "letters from 1850-1870", "Victorian (1837-1901) postcards", "shifts 0700-1900", "open 0900-1700 weekdays",
    "terrain à 12 000 000 FCFA", "Preis 12.500.000 Rupiah", "€12 500 000 or near offer",
    "reunion for classes 1996 2006 2016", "pages 1203-1288 need scanning",
    "Walking partner wanted, Tuesdays and Thursdays 09.30-10.30, flat paths.",
    # a 24-hour span off the hour, and a range of amounts in thousands before a unit, which folding dashes
    # turned into a refusal (review)
    "open 0830-1730 weekdays", "shifts 0730-1545", "budget 15 000–20 000 €", "Budget 15.000–20.000 Euro",
    "25 000–30 000 km", "salaire 35 000-40 000 euros",
    # ...and without a unit, or with one not listed: folding dashes made these rents and salaries refusals (review)
    "loyer 1 200–1 500 par mois", "Miete 1.200–1.500 warm", "Gehalt 45.000–55.000 im Jahr",
    "budget 10 000–15 000 kr", "salary 45 000–55 000 SEK", "Budżet 3 000–4 000 zł", "10 000–15 000 CHF"])
def test_dates_times_ranges_and_amounts_are_not_phone_numbers(text):
    """Each was refused as a phone number: dotted and day-first dates, dotted and 24-hour times, ranges, and
    thousands written with spaces or dots — a round trip each, for ordinary needs (audit)."""
    assert guard.identifies(text, **ME) is None


@pytest.mark.parametrize("text", [
    "612 345 678", "612.345.678", "call 06.12.34.56.78", "ring 0161 496 0000 on 23.09.2026",
    "call 9123 4567", "0161 1500-2000", "09.30 07700 900123", "2012 2045 3000", "1996 2006 07700900123",
    "ISBN 978-0-306-40615-7 07700 900123", "grid ref TQ 30012 80456 07700 900123", "0700-1900 07700900123",
    # the first fix read any pair of HHMM values as a time range, and a unit or currency blanked the front or
    # back of a number grouped in threes (review)
    "call 2123-2345", "call 2222-2222", "Costa Rica: 2222-1234", "07700 900 123 rupees", "0161 496 000 km",
    "₦ 803 123 4567", "07700 900 123-456 789 km",
    # what keeps a time range, a span of years and a round range narrow (review)
    "call 9900-9915", "call 1850-1234", "call 300-770000",
    # two separators between groups, or a country code before a unit, let an exemption blank a piece (review)
    "+44 6111 - 1542 - 2093", "0413  2039  1826", "07700  1996  2006", "+34 612 345 678 km",
    "call +34 612 345 678 euros"])
def test_what_a_phone_number_looks_like_is_still_refused(text):
    """The exemptions above must not swallow a real number, nor a piece of one."""
    assert guard.identifies(text, **ME)


@pytest.mark.parametrize("name, text", [
    ("Grace Park", "Meet at Finsbury Park on Sunday"), ("Sunday Adeyemi", "Free on Sunday afternoons"),
    ("May Chen", "Moving house in May"), ("May Chen", "May I ask for a lift?"),
    ("Hope Mensah", "Hope someone can help with a sofa!"), ("Tom King", "near King's Cross station"),
    ("Mark Evans", "Mark my words, it is a bargain"), ("Ali Khan", "Khan Academy tutor wanted"),
    ("Margaret Hale", "near Margaret Street library"), ("Margaret Hale", "Hale and hearty at 67"),
    ("Will Young", "Will you be around? my person will be"), ("Will Young", "Will I need a car?"),
    ("Mark Evans", "Mark as done, thanks"),
    # a weekday or a month beside a day's number, after one, in a list or a choice, or after mid- (review)
    ("May Chen", "Free May 3rd onwards"), ("May Chen", "free 3 May onwards"), ("May Chen", "Deadline 23 May"),
    ("Sunday Adeyemi", "free Sunday 14th"), ("Sunday Adeyemi", "free Saturday or Sunday"),
    ("Sunday Adeyemi", "Saturday, Sunday or Monday"), ("Sunday Adeyemi", "weekends (Saturday/Sunday) only"),
    ("Sunday Adeyemi", "Sunday mornings work best"), ("May Chen", "April or May"),
    ("May Chen", "between April and May"), ("May Chen", "starting May 2027"), ("May Chen", "mid-May"),
    ("Hope Mensah", "Hope this helps"), ("June Lee", "Available from June"), ("May Chen", "Sunday and May work"),
    ("May Chen", "free until May"), ("May Chen", "April to May"), ("Summer Jones", "Summer camp helpers wanted"),
    ("Sunny Patel", "Sunny weather, garden party"), ("Margaret Hale", "near Margaret Road"),
    ("Victoria Adams", "Victoria Station car park"), ("Victoria Adams", "Victoria Library has it"),
    ("Margaret Hale", "Margaret Avenue bus stop"), ("Victoria Adams", "Victoria Square"),
    ("Victoria Adams", "Victoria Gardens"),
    # a middle-name gap joined two name words, each a word here, across a full stop or comma (review)
    ("Sunday Park", "Free on Sunday, Finsbury Park works"), ("May Park", "Moving in May, Finsbury Park area")])
def test_an_everyday_word_is_not_the_writers_name(name, text):
    """A word of the writer's name refused any text where it was capitalised: a weekday, a month, the start of
    a sentence, a place (audit). Someone named Sunday, May, Hope or Grace could not write an ordinary need."""
    assert guard.identifies(text, name=name) is None


@pytest.mark.parametrize("name, text", [
    ("Grace Park", "ask Grace about the sofa"), ("Hope Mensah", "my person Hope is keen"),
    ("Tom King", "Tom here, keen"), ("Will Young", "ask Will about it"), ("Ali Khan", "ask Dr Khan"),
    ("Mark Evans", "Evans here, keen"), ("Maya Chen", "Maya C. is looking"),
    # A place that is also the name, standing alone, cannot be told from the name: still refused (audit)
    ("Jordan Lee", "just back from Jordan"),
    # The first fix read any capitalised neighbour as a longer proper name, so a middle name, a title, a heading
    # in Title Case or capitals, another surname or a weekday let the name through (review)
    ("Maya Chen", "my person is Maya Jane Chen"), ("Maya Chen", "I'm Maya Li Chen, a nurse"),
    ("Mary Smith", "Mary Anne Smith here"), ("Maya Chen", "Maya Needs Help Moving A Sofa"),
    ("Maya Chen", "MAYA NEEDS A LIFT"), ("Maya Chen", "Hi All, Maya Here"), ("Maya Chen", "Maya's Moving Day"),
    ("Maya Chen", "Maya's Kitchen needs a helper"), ("Maya Chen", "I study with Professor Chen"),
    ("Maya Chen", "ask Doctor Chen"), ("Maya Chen", "Chen Family needs a van"), ("Maya Chen", "ask Coach Maya"),
    ("Maya Chen", "ask Grandma Maya"), ("Maya Chen", "I'm Maya Okafor now"), ("Tom King", "ask Tom Tuesday"),
    ("Kofi Mensah", "Signed, Kofi Annan"), ("Grace Park", "ask Coach Grace"), ("Grace Park", "Grace Anne Park here"),
    # ...and a first name that is a weekday or a month was never checked at all (review)
    ("May Chen", "ask May about it"), ("June Lee", "June here, keen"),
    ("Sunday Adeyemi", "my person Sunday is keen"), ("April Jones", "ask April about it"),
    # ...and an everyday word opening a sentence let through the commonest slip, a need in the third person
    # that starts with the person's first name (review)
    ("Sue Brown", "Sue is looking for a walking partner"),
    ("Sue Brown", "Sue, 67, retired nurse, wants a walking partner"),
    ("Jack Wilson", "Jack here, looking for a climbing partner"), ("Frank Osei", "Frank (72) needs help"),
    ("Rose Adams", "Rose is a retired teacher"), ("Hope Mensah", "Hope here, keen to help"),
    # ...but only for a short list of words after it, so any other verb, a joiner, a colon or dash, a surname or
    # an initial, and a sign-off let the name through (review)
    ("Sue Brown", "Sue loves gardening and wants help"), ("Sue Brown", "Sue and her dog need a lift"),
    ("Sue Brown", "Sue: retired nurse, wants a walking partner"), ("Sue Brown", "Sue - retired nurse"),
    ("Sue Brown", "Sue seeks a walking partner"), ("Sue Brown", "Sue lives in Leeds"), ("Sue Brown", "Sue x"),
    ("Sue Brown", "Sue."), ("Sue Brown", "Regards,\nSue"), ("Sue Brown", "Lovely, see you then.\n\nSue"),
    ("Sue Brown", "Happy to help with that. Thanks! — Sue"), ("Jack Wilson", "Jack looking for a climbing partner"),
    ("Jack Wilson", "Happy to help with the van.\nBest,\nJack"), ("Jack Wilson", "- Jack"),
    ("Jack Wilson", "Jack: 3 bed flat wanted near the station"), ("Grace Park", "Thanks so much! — Grace"),
    ("Grace Park", "Grace: 34, nurse, looking for a climbing partner"), ("Grace Park", "Grace P. here"),
    ("Grace Park", "Grace and I are looking for a flat"), ("Grace Park", "Grace offers tutoring"),
    ("Hope Mensah", "Thank you!\nHope"), ("Hope Mensah", "Hope looking for a sofa"), ("Hope Mensah", "Hope says hi"),
    ("Rose Adams", "Thanks,\nRose x"), ("Rose Adams", "Rose can help with sewing"),
    ("Will Young", "Sounds good.\nWill"), ("Will Young", "Will looking for a bandmate"),
    ("Will Young", "Will and I are looking for a cleaner"), ("May Chen", "Thanks!\nMay"),
    ("May Chen", "May lives near Leeds"), ("May Chen", "May and her son need a lift"), ("June Lee", "Thanks!\nJune"),
    ("June Lee", "June seeks a lift"), ("April Jones", "April looking for a flatmate"),
    ("Sunday Adeyemi", "Sunday looking for a tutor"), ("Sunday Adeyemi", "Sunday runs a food stall"),
    ("Frank Osei", "Frank and his wife need help moving"), ("Mark Evans", "Mark Taylor here"),
    ("Mark Evans", "Mark lives in Hackney"), ("Lee Wong", "Lee looking for badminton partner"),
    ("Grace Park", "Park family needs a sitter"),
    # ...and a greeting before it, a number after a weekday or month that is an age, not a day (review)
    ("Grace Park", "Thanks Grace"), ("Sue Brown", "Love Sue"), ("Hope Mensah", "Hi Hope here"),
    ("June Lee", "June 34 wants a walk"), ("May Chen", "May 67 retired"),
    # ...and a surname that is also a place word, or a business named after its owner (review)
    ("Maya Chen", "Maya Park is looking for a tutor"), ("Maya Chen", "Dear Maya Park, thanks"),
    ("Maya Chen", "Maya Hall here"), ("Maya Chen", "I'm Maya Green now"), ("Maya Chen", "ask Maya Park"),
    ("Mark Evans", "I'm Mark Hall"), ("Grace Park", "Grace Hill here"), ("Sue Brown", "Sue's Kitchen needs a helper"),
    ("Sue Brown", "Sue's Café needs a hand"), ("Grace Park", "Grace's Bakery is hiring"),
    ("Maya Chen", "Maya Kitchen needs a helper"),
    # ...and a sentence-opening name followed by a kiss, a listed verb, an adverb, a past tense or another name,
    # which base refused (review)
    ("May Chen", "Thanks!\nMay x"), ("Hope Mensah", "Hope x"), ("Will Young", "Cheers\nWill x"),
    ("Summer Jones", "Thanks! Summer xx"), ("Mark Evans", "Mark x"), ("June Lee", "Lovely, see you Sunday.\nJune xx"),
    ("May Chen", "May can help"), ("Hope Mensah", "Hope is keen"), ("Hope Mensah", "Hope just moved here"),
    ("Mark Evans", "Mark could use a hand"), ("Mark Evans", "Mark also needs a lift"),
    ("Mark Evans", "Mark will drive"), ("Hope Mensah", "Hope would love a lift"),
    ("Hope Mensah", "Hope from Leeds needs a lift"),
    ("Hope Mensah", "Hope used to teach piano"), ("Hope Mensah", "Hope and Tom need a van"),
    ("Mark Evans", "Mark and Jo need a van"), ("Mark Evans", "Mark had a van"), ("Mark Evans", "Mark cannot drive"),
    ("Will Young", "Will should be free"), ("Will Young", "Will moved to Leeds last year"),
    ("Will Young", "Will aged 70 needs a lift"), ("Mark Evans", "Mark with his dog needs a walker"),
    ("Mark Evans", "• Mark needs help"),
    # ...and a sign-off or a heading in Title Case before a given name, or a greeting before "from" (review)
    ("Jack Wilson", "Kind Regards Jack"), ("Grace Park", "Many Thanks Grace"), ("Rose Adams", "Posted By Rose"),
    ("Sue Brown", "Help Wanted By Sue"), ("June Lee", "Love from June"),
    ("June Lee", "Thanks so much.\nLove from June x"), ("April Jones", "Best wishes from April"),
    ("Sunday Adeyemi", "Greetings from Sunday!"),
    ("June Lee", "on behalf of June, my person")])
def test_the_name_written_as_a_name_is_still_refused(name, text):
    assert guard.identifies(text, name=name)


def test_a_long_text_is_read_in_bounded_time():
    """Looking back from each word of the name scanned the whole text before it: a crafted 2000-character need
    held the lock everyone shares for over a second, and a refusal counts against no daily cap (review)."""
    text = ("a" * 1400 + "-" + ", Bb Grace" * 66)[:1980] + " x@y.co"
    start = time.perf_counter()
    assert guard.identifies(text, name="Grace Park")
    assert time.perf_counter() - start < 0.2
    # Folding a compatibility character can make six of one: the email shape then scanned 12,000 characters
    # from every start (review).
    start = time.perf_counter()
    assert guard.identifies("㌖" * 1988 + " 07700900123", **ME)
    assert time.perf_counter() - start < 0.2


@pytest.mark.parametrize("name", [" ".join(["Ab"] * 26) + " Q", " ".join(["Ab"] * 25) + " Zz"])
def test_a_crafted_name_is_read_in_bounded_time(name):
    """A gap for middle names between the words of the name tried about three ways per word: a member who set
    their own name to 'Ab Ab … Ab Q' held the lock everyone shares for as long as they liked with one need (review)."""
    start = time.perf_counter()
    guard.identifies(("Ab " * 700)[:2000], name=name)
    assert time.perf_counter() - start < 0.2


@pytest.mark.parametrize("text", [
    "ISBN 978-0-306-40615-7, anyone have it?", "ISBN 0-306-40615-X", "EAN 4006381333931",
    "found dog at 51.50740 -0.12780", "grid ref TQ 30012 80456", "frame no. 123456789 stolen bike",
    "serial 12345678", "see you @6pm", "see you @6PM", "meet @the library", "back @ 7", "in by @10:30",
    "lunch @noon"])
def test_codes_coordinates_and_times_are_not_contacts(text):
    """A book's ISBN, a lost dog's coordinates, a stolen bike's frame number and '@6pm' were refused as a phone
    number or a handle (audit)."""
    assert guard.identifies(text, **ME) is None


@pytest.mark.parametrize("text", [
    "@2fast4you on insta", "@99problems", "DM me @4ever_maya", "follow @my.kitchen.ldn", "@the.real.maya",
    "@home.bakes"])
def test_a_handle_is_still_a_handle(text):
    """Keeping '@6pm' and '@the library' out let every handle starting with a digit or a stop word through (review)."""
    assert guard.identifies(text, **ME)


@pytest.mark.parametrize("text", ["the dot.com bubble", "asp.net developer", "vb.net help"])
def test_a_bare_lower_case_domain_is_refused_even_when_it_is_a_word(text):
    """The price of catching mayachen.dev without a path, recorded so it is a choice (review)."""
    assert guard.identifies(text, **ME)


@pytest.mark.parametrize("name, contact, text", [
    # Accents dropped, names in scripts without spaces or case, a name run together, a look-alike letter (#32):
    # deferred until a live slip is seen, since folding them risks refusing ordinary words.
    ("José García", "", "soy Jose Garcia"), ("陈玛雅", "", "我是陈玛雅，想找"),
    ("Maya Chen", "", "my person is MayaChen"), ("Maya Chen", "", "my person is Mаya"),
    # A name word that is an everyday word or a date reads as that word after another capitalised word, after
    # a word that goes before dates or beside another date, or when a word that is often an opener (Hope, Will,
    # May, Mark, a season, a weekday, a month) opens a sentence and goes on with a lower-case word that is
    # neither a verb ending in s nor another listed one (#31): the price of "Finsbury Park", "free on Sunday"
    # and "Hope someone can help". A name word with a place word after it reads as the place ("Khan Academy",
    # "Margaret Street"), and Street and Cross are also surnames.
    ("Grace Park", "", "my person, Kelly Grace, is keen"), ("Sunday Adeyemi", "", "a message from Sunday"),
    ("Grace Park", "", "my person, Kelly Grace Anne Park"), ("Elizabeth Brown", "", "I'm Liz Brown"),
    ("Sunday Adeyemi", "", "Sunday recently moved here"),
    ("Hope Mensah", "", "Hope someone asks for me"), ("Will Young", "", "Will need a lift on Friday"),
    ("Sunday Adeyemi", "", "ask Sunday or Monday"), ("Ali Khan", "", "ask at Khan Academy"),
    ("Maya Chen", "", "I'm Maya Street now"),
    # Upper-case links, a bare .io, .ai or capitalised domain: library, product and brand names (socket.io,
    # claude.ai, ASP.NET, Booking.com) look the same.
    ("", "", "GITHUB.COM/MAYA"), ("", "", "portfolio: mayachen.io"), ("", "", "maya.ai"),
    ("", "", "Portfolio: Mayachen.dev"), ("", "", "mayachen.art"), ("", "", "maya.page"),
    # 7-digit numbers and labelled 8-digit ones (#50): deferred; a 7-digit shape is too common in prices,
    # codes and counts to refuse, and nobody has slipped one yet.
    ("", "", "call 555 0142"), ("", "", "Iceland: hringdu 581 2345"), ("", "", "office 2012-3456"),
    ("", "", "WhatsApp #91234567"),
    # ...and 8-digit numbers that read as a time range, a list of years or a round range, as shifts, classes and
    # rents do.
    ("", "", "call 2130-1845"), ("", "", "call 2012 2045"), ("", "", "call 3000-3400"),
    # Deliberate evasion always wins (#69): the guard is a seatbelt for an assistant that slips, not a wall.
    ("", "", "call seven seven zero zero nine zero zero one two three"), ("", "", "call O77OO9OO123"),
    ("", "", "maya (at) example (dot) com"), ("", "", "I'm the head chef at The Wolseley"),
    # A label, a currency or a time glued to a number is read as a code, an amount or a time.
    ("", "", "serial 07700900123"), ("", "", "£612 345 678"), ("", "", "text 07.12 34 56 78"),
    # The writer's own contact written another way (#33): out of this stage's scope; only the stored string
    # and the generic shapes are caught.
    ("", "mayabuilds on Instagram", "Instagram: mayabuilds"), ("", "mayachen99@example.com", "write to mayachen99")])
def test_known_passes(name, contact, text):
    """What the guard does not catch, on purpose or not yet, so a change that starts catching one is noticed."""
    assert guard.identifies(text, name=name, contact=contact) is None
