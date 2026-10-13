"""Fast rule-based understanding of voice commands (no LLM call, near-zero latency).

The LLM (Qwen/Mistral) is only consulted when these rules cannot make sense of a message,
which is how we keep both latency and token usage low.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
TAG_WORDS = {
    "spicy", "sweet", "light", "healthy", "crispy", "creamy", "cold", "hot",
    "filling", "cheesy", "tangy", "smoky",
}
CATEGORY_WORDS = {
    "starter": "starter", "starters": "starter", "appetizer": "starter", "appetizers": "starter",
    "main": "main", "mains": "main", "curry": "main", "curries": "main",
    "rice": "rice", "bread": "bread", "breads": "bread",
    "dessert": "dessert", "desserts": "dessert", "sweets": "dessert",
    "drink": "drink", "drinks": "drink", "beverage": "drink", "beverages": "drink",
    "snack": "snack", "snacks": "snack",
}
INTENTS = {
    "add_item", "remove_item", "show_cart", "clear_cart", "recommend", "show_menu",
    "place_order", "confirm", "deny", "set_diet", "set_address", "greet", "help",
    "thanks", "chitchat", "discover_places", "find_recipes", "food_buzz", "unknown",
}

_VERBS = (
    r"i want to order|i'd like to order|i would like to order|i want|i need|i'd like|i would like|"
    r"i'll have|i will have|i'll take|give me|bring me|get me|add|order|get"
)
_FILLER = r"(?:(?:please|kindly|hey|ok|okay|so|also|and|can you|could you|would you|will you)\s+)*"
_ADD_LEAD = re.compile(rf"^{_FILLER}(?:{_VERBS})\s+(?:also\s+)?")
_REMOVE_LEAD = re.compile(rf"^{_FILLER}(?:remove|delete|take out|drop)\s+")
_TAIL = re.compile(
    r"\s*\b(?:(?:to|into|in|from|on)\s+(?:my|the)\s+(?:cart|order|basket|bag|list)|for me|please|thanks|thank you)\b.*$"
)
_QTY = re.compile(r"^(\d+|" + "|".join(NUMBER_WORDS) + r")\s+(.+)$")

_P = lambda pattern: re.compile(pattern)  # noqa: E731
_CONFIRM = _P(r"^(yes|yeah|yep|yup|sure|confirm|confirmed|correct|ok|okay|go ahead|do it|place it|haan|ha)\b")
_DENY = _P(r"^(no|nope|nah|nahi|not now|stop|cancel that|don't|do not)\b")
_PLACE = _P(r"\b(place|confirm|finali[sz]e|submit)\b.*\border\b|\bcheck ?out\b|\border now\b|\bthat'?s (all|it)\b|\bi'?m done\b")
_CLEAR = _P(r"\b(clear|empty|reset)\b.*\b(cart|order|basket)\b|\bstart over\b|\bcancel (my |the )?order\b")
_DISCOVER_PLACES = _P(r"\b(restaurants?|food places?|places to eat|food spots|where can i eat|nearby restaurants?)\b")
_FIND_RECIPES = _P(r"\b(recipes?|how (?:do i|to) cook|cooking ideas)\b")
_FOOD_BUZZ = _P(r"\b(reddit|trending|food buzz|popular discussions|what are people saying)\b")
_RECOMMEND = _P(
    r"\b(recommend|recommendation|suggest|suggestion|surprise me|what should i (eat|order|have)|"
    r"what'?s good|i'?m hungry|i am hungry|what do you recommend|something (spicy|sweet|light|cheesy|"
    r"crispy|cold|hot|healthy|filling|tangy|creamy|tasty|good|nice))\b"
)
_MENU = _P(r"\b(menu|what (?:\w+ )?do you have|what'?s available|what can i (get|order)|options|categories)\b")
_CART = _P(r"\b(show|view|see|read|what'?s in|whats in|what is in)\b.*\b(cart|basket|order)\b|^(my )?(cart|basket)$|\bhow much\b|\btotal\b")
_DIET = _P(
    r"\b(?:i am|i'm|im|i eat|we are|i only eat|i'm only|i am only)\b.*?"
    r"\b(non[- ]?veg(?:etarian)?|vegetarian|vegan|veg|everything|anything)\b"
)
_ADDRESS = re.compile(r"\b(?:deliver(?:y)?(?: it)? to|my address is|address is|ship to|send it to)\s+(.+)$", re.I)
_GREET = _P(r"^(hi|hello|hey|namaste|good (morning|afternoon|evening))\b")
_HELP = _P(r"\b(help|what can you do|how does this work)\b")
_THANKS = _P(r"\b(thanks|thank you|bye|goodbye|see you)\b")


@dataclass
class Parsed:
    intent: str = "unknown"
    items: list[dict] = field(default_factory=list)  # {"phrase": str, "qty": int | None}
    tags: list[str] = field(default_factory=list)
    diet: str | None = None
    address: str | None = None


def normalize(text: str) -> str:
    t = text.lower().replace("\u2019", "'")
    t = re.sub(r"[^a-z0-9'&, ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def extract_tags(t: str) -> list[str]:
    tags: list[str] = []
    for word in re.findall(r"[a-z]+", t):
        tag = word if word in TAG_WORDS else CATEGORY_WORDS.get(word)
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def extract_items(text: str) -> list[dict]:
    """Split 'two naan and a paneer tikka' into [{'phrase': 'naan', 'qty': 2}, ...]."""
    s = _TAIL.sub("", text).strip(" ,")
    items: list[dict] = []
    for part in re.split(r"\s*(?:,|&|\band\b|\bplus\b)\s*", s):
        part = part.strip()
        if not part:
            continue
        qty: int | None = None
        m = _QTY.match(part)
        if m:
            raw = m.group(1)
            qty = int(raw) if raw.isdigit() else NUMBER_WORDS[raw]
            qty = max(1, min(qty, 20))
            part = m.group(2).strip()
        if part and len(part.split()) <= 6:
            items.append({"phrase": part, "qty": qty})
    return items


def parse(raw: str) -> Parsed:
    t = normalize(raw)
    words = t.split()
    if not t:
        return Parsed()

    if len(words) <= 6 and _CONFIRM.match(t):
        return Parsed("confirm")
    if len(words) <= 6 and _DENY.match(t):
        return Parsed("deny")
    if _PLACE.search(t):
        return Parsed("place_order")
    if _CLEAR.search(t):
        return Parsed("clear_cart")
    # Specific discovery intents must be checked before generic recommendation/menu rules.
    if _DISCOVER_PLACES.search(t):
        return Parsed("discover_places", tags=extract_tags(t))
    if _FIND_RECIPES.search(t):
        return Parsed("find_recipes", tags=extract_tags(t))
    if _FOOD_BUZZ.search(t):
        return Parsed("food_buzz", tags=extract_tags(t))
    if _RECOMMEND.search(t):
        return Parsed("recommend", tags=extract_tags(t))
    if _MENU.search(t):
        return Parsed("show_menu", tags=extract_tags(t))
    if _CART.search(t):
        return Parsed("show_cart")
    if _REMOVE_LEAD.match(t):
        return Parsed("remove_item", items=extract_items(_REMOVE_LEAD.sub("", t, count=1)))
    m = _DIET.search(t)
    if m:
        word = m.group(1).replace(" ", "").replace("-", "")
        diet = "non-veg" if word.startswith("nonveg") else "any" if word in {"everything", "anything"} else "veg"
        return Parsed("set_diet", diet=diet)
    m = _ADDRESS.search(raw.strip())
    if m:
        address = m.group(1).strip(" .,")[:200]
        if address:
            return Parsed("set_address", address=address[0].upper() + address[1:])
    if _GREET.match(t):
        return Parsed("greet")
    if _HELP.search(t):
        return Parsed("help")
    if _THANKS.search(t):
        return Parsed("thanks")
    if _ADD_LEAD.match(t):
        return Parsed("add_item", items=extract_items(_ADD_LEAD.sub("", t, count=1)))
    # Unknown so far: keep candidate items so the graph can still treat "butter naan" as an add.
    items = extract_items(t) if len(words) <= 8 else []
    return Parsed("unknown", items=items, tags=extract_tags(t))
