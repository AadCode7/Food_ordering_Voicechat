"""The ordering agent, built with LangGraph.

    START -> understand -> (route by intent) -> <handler> -> finalize -> END

* `understand` uses fast rules first and only falls back to the open-source LLM when needed.
* Handlers are plain, deterministic functions (cart, recommendations, order placement).
* Replies are templated, so the happy path needs zero LLM tokens.
"""
from __future__ import annotations

import copy
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from api.models.orm import Order
from api.services import external_apis, llm_service, menu_service, profile_service, recommend_service
from logger import get_logger, log_event, span
from utils import nlp
from utils.metrics import metrics

log = get_logger("graph")
MAX_LINE_QTY = 20


class OrderState(TypedDict, total=False):
    message: str
    user: dict
    session: dict
    intent: str
    entities: dict
    source: str
    reply: str
    suggestions: list
    order: dict


# ----------------------------------------------------------------- helpers
def _db(config: RunnableConfig):
    return config["configurable"]["db"]


def total(cart: list[dict]) -> int:
    return sum(line["price"] * line["qty"] for line in cart)


def _describe(cart: list[dict]) -> str:
    return ", ".join(f'{line["qty"]} {line["name"]}' for line in cart)


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _node(name: str):
    def deco(fn):
        def wrapper(state: OrderState, config: RunnableConfig):
            with span(f"graph.{name}", intent=state.get("intent", "")):
                return fn(state, config)

        wrapper.__name__ = name
        return wrapper

    return deco


# ------------------------------------------------------------------- nodes
@_node("understand")
def understand(state: OrderState, config: RunnableConfig) -> dict:
    parsed = nlp.parse(state["message"])
    diet = state["user"].get("diet", "any")
    source = "rule"
    intent, items, tags = parsed.intent, parsed.items, parsed.tags

    if intent == "unknown" and items:  # a bare dish name such as "butter naan"
        matched, _ = menu_service.resolve_items(items, diet)
        if matched:
            intent = "add_item"
    elif intent in {"add_item", "remove_item"}:
        matched, _ = menu_service.resolve_items(items, diet)
        if not matched:
            intent = "unknown"  # rules could not find any dish -> ask the LLM

    if intent == "unknown" and llm_service.available():
        guess = llm_service.understand(state["message"])
        if guess:
            intent, items, tags, source = guess["intent"], guess["items"], guess["tags"] or tags, "llm"
    if intent == "unknown":
        intent = "chitchat"

    log_event(log, "intent", intent=intent, source=source)
    metrics.inc(f"intent.{intent}")
    metrics.inc(f"understand.{source}")
    return {
        "intent": intent,
        "source": source,
        "entities": {"items": items, "tags": tags, "diet": parsed.diet, "address": parsed.address},
    }


def _route(state: OrderState) -> str:
    return {
        "add_item": "add_item", "remove_item": "remove_item", "show_cart": "show_cart",
        "clear_cart": "clear_cart", "recommend": "recommend", "show_menu": "show_menu",
        "place_order": "place_order", "confirm": "confirm", "deny": "deny",
        "set_diet": "set_profile", "set_address": "set_profile",
        "discover_places": "discover_places", "find_recipes": "find_recipes", "food_buzz": "food_buzz",
    }.get(state["intent"], "smalltalk")


@_node("add_item")
def add_item(state: OrderState, config: RunnableConfig) -> dict:
    session = copy.deepcopy(state["session"])
    diet = state["user"].get("diet", "any")
    matched, missing = menu_service.resolve_items(state["entities"]["items"], diet)
    cart: list[dict] = session["cart"]
    added, blocked = [], []
    for item, qty in matched:
        qty = qty or 1
        if diet == "veg" and not item["veg"]:
            blocked.append(item["name"])
            continue
        line = next((c for c in cart if c["id"] == item["id"]), None)
        if line:
            line["qty"] = min(MAX_LINE_QTY, line["qty"] + qty)
        else:
            cart.append({"id": item["id"], "name": item["name"], "qty": min(qty, MAX_LINE_QTY),
                         "price": item["price"], "veg": item["veg"]})
        added.append(f"{qty} {item['name']}")
    session["pending_confirm"] = False
    parts = []
    if added:
        parts.append(f"Added {_join(added)}.")
    if blocked:
        parts.append(f"{_join(blocked)} is non-veg, so I skipped it because you eat vegetarian.")
    if missing:
        parts.append(f"I couldn't find {_join(missing)} on the menu.")
    if cart:
        parts.append(f"Your total is {total(cart)} rupees. Anything else, or say place order.")
    else:
        parts.append("Tell me what you'd like, or say recommend.")
    return {"reply": " ".join(parts), "session": session}


@_node("remove_item")
def remove_item(state: OrderState, config: RunnableConfig) -> dict:
    session = copy.deepcopy(state["session"])
    matched, missing = menu_service.resolve_items(state["entities"]["items"], state["user"].get("diet", "any"))
    cart: list[dict] = session["cart"]
    removed, absent = [], []
    for item, qty in matched:
        line = next((c for c in cart if c["id"] == item["id"]), None)
        if not line:
            absent.append(item["name"])
        elif qty and qty < line["qty"]:
            line["qty"] -= qty
            removed.append(f"{qty} {item['name']}")
        else:
            cart.remove(line)
            removed.append(item["name"])
    session["pending_confirm"] = False
    parts = []
    if removed:
        parts.append(f"Removed {_join(removed)}.")
    if absent:
        parts.append(f"{_join(absent)} wasn't in your cart.")
    if missing:
        parts.append(f"I couldn't find {_join(missing)} on the menu.")
    parts.append(f"Your total is {total(cart)} rupees." if cart else "Your cart is empty now.")
    return {"reply": " ".join(parts), "session": session}


@_node("show_cart")
def show_cart(state: OrderState, config: RunnableConfig) -> dict:
    cart = state["session"]["cart"]
    if not cart:
        return {"reply": "Your cart is empty. Try saying add two butter naan, or ask me to recommend something."}
    return {"reply": f"You have {_describe(cart)}. The total is {total(cart)} rupees."}


@_node("clear_cart")
def clear_cart(state: OrderState, config: RunnableConfig) -> dict:
    session = copy.deepcopy(state["session"])
    session["cart"], session["pending_confirm"] = [], False
    return {"reply": "Okay, I cleared your cart. What would you like instead?", "session": session}


@_node("recommend")
def recommend(state: OrderState, config: RunnableConfig) -> dict:
    cart_ids = {c["id"] for c in state["session"]["cart"]}
    picks = recommend_service.recommend(state["user"], state["entities"]["tags"], limit=4, exclude=cart_ids)
    if not picks:
        return {"reply": "I couldn't find a match. Try asking for the menu.", "suggestions": []}
    names = [f'{p["name"]} for {p["price"]} rupees' for p in picks[:3]]
    lead = "Since you order it often, I'd suggest" if picks[0]["reason"] == "You order this often" else "I'd suggest"
    return {"reply": f"{lead} {_join(names)}. Say add and the dish name to order.", "suggestions": picks}


@_node("show_menu")
def show_menu(state: OrderState, config: RunnableConfig) -> dict:
    diet = state["user"].get("diet", "any")
    cats = [t for t in state["entities"]["tags"] if t in menu_service.categories()]
    if cats:
        items = menu_service.list_menu(category=cats[0], diet=diet)[:6]
        reply = f"For {cats[0]} we have " + _join([i["name"] for i in items]) + "."
        return {"reply": reply, "suggestions": [{"id": i["id"], "name": i["name"], "price": i["price"],
                                                 "veg": i["veg"], "category": i["category"], "reason": ""} for i in items]}
    return {"reply": "We have " + _join(menu_service.categories()) + ". Ask for a category, or say recommend."}



def _discovery_query(message: str, intent: str) -> str:
    """Strip request wording and a trailing location while preserving food/topic terms."""
    text = message.lower()
    text = re.sub(r"\b(?:in|near|around)\s+(?:me|my area|here|[a-z][a-z\s,-]{1,50})$", " ", text)
    patterns = (
        r"\b(?:what are people saying|can you find|show me|search for|"
        r"find|search|show|look for|recommend|please|tell me|what are|what is|any|good|best|"
        r"nearby|near me|around me|in my area|restaurants?|food places?|places to eat|food spots|"
        r"where can i eat|recipes?|how do i cook|how to cook|cooking ideas|reddit|trending|"
        r"food buzz|popular discussions|about|for|of|in)\b"
    )
    text = re.sub(patterns, " ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.?")
    if intent == "discover_places":
        return text or "restaurants"
    return text or ("food" if intent == "food_buzz" else "Indian food")


def _location_for(state: OrderState) -> str:
    match = re.search(r"\b(?:in|near|around)\s+([a-z][a-z\s,-]{1,50})$", state["message"], re.I)
    if match:
        candidate = match.group(1).strip(" ,.")
        if candidate.lower() not in {"me", "my area", "here"}:
            return candidate[:80]
    return (state["user"].get("address") or "Nashik")[:80]


@_node("discover_places")
def discover_places(state: OrderState, config: RunnableConfig) -> dict:
    query = _discovery_query(state["message"], "discover_places")
    location = _location_for(state)
    # Run both providers concurrently; provider adapters already apply timeouts and fail-soft behavior.
    with ThreadPoolExecutor(max_workers=2) as pool:
        google_future = pool.submit(external_apis.google_places, f"{query} in {location}", 3)
        yelp_future = pool.submit(external_apis.yelp, query, location, 3)
        google, yelp = google_future.result(), yelp_future.result()
    combined, seen = [], set()
    for result in (google, yelp):
        if not result.get("available"):
            continue
        for place in result.get("results", []):
            name = (place.get("name") or "").strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                combined.append(place)
    if not google.get("available") and not yelp.get("available"):
        return {"reply": "Restaurant discovery is not configured yet. Add Google Places or Yelp credentials to enable it; food ordering still works."}
    if not combined:
        return {"reply": f"I couldn't find restaurant results for {query} in {location}. Try another cuisine or location."}
    lines = []
    for place in combined[:3]:
        detail = []
        if place.get("rating") is not None:
            detail.append(f'rating {place["rating"]}')
        if place.get("price"):
            detail.append(str(place["price"]))
        if place.get("address"):
            detail.append(place["address"])
        lines.append(place["name"] + (f' ({", ".join(detail)})' if detail else ""))
    return {"reply": f"Here are a few options for {query} in {location}: " + "; ".join(lines) + ". Check current hours and availability before visiting."}


@_node("find_recipes")
def find_recipes(state: OrderState, config: RunnableConfig) -> dict:
    query = _discovery_query(state["message"], "find_recipes")
    data = external_apis.spoonacular(query, limit=3)
    if not data.get("available"):
        return {"reply": "Recipe search is not configured yet. Add a Spoonacular API key to enable it; local menu recommendations still work."}
    recipes = [r.get("title") for r in data.get("results", []) if r.get("title")]
    if not recipes:
        return {"reply": f"I couldn't find recipes for {query}. Try a simpler ingredient or dish name."}
    return {"reply": f"Recipe ideas for {query}: " + "; ".join(recipes[:3]) + ". These are recipe suggestions, not items currently available to order."}


@_node("food_buzz")
def food_buzz(state: OrderState, config: RunnableConfig) -> dict:
    query = _discovery_query(state["message"], "food_buzz")
    data = external_apis.reddit(query, limit=3)
    if not data.get("available"):
        return {"reply": "Food discussion search is not configured yet. Add Reddit API credentials to enable it; local menu recommendations still work."}
    lines = []
    for post in data.get("results", [])[:3]:
        title, url = post.get("title"), post.get("url")
        if title:
            lines.append(f"{title}" + (f" ({url})" if url else ""))
    if not lines:
        return {"reply": f"I couldn't find food discussions about {query}. Try a different search phrase."}
    return {"reply": f"Food discussions about {query}: " + "; ".join(lines) + ". Reddit posts are community opinions, not verified restaurant availability."}


@_node("place_order")
def place_order(state: OrderState, config: RunnableConfig) -> dict:
    session = copy.deepcopy(state["session"])
    cart = session["cart"]
    if not cart:
        return {"reply": "Your cart is empty. Add something first."}
    address = state["user"].get("address")
    if not address:
        return {"reply": "Where should I deliver? Say deliver to, followed by your address, or save it in your profile."}
    session["pending_confirm"] = True
    return {
        "session": session,
        "reply": (f"You have {_describe(cart)}, total {total(cart)} rupees, delivering to {address}. "
                  "Payment is cash on delivery. Say yes to confirm or no to cancel."),
    }


@_node("confirm")
def confirm(state: OrderState, config: RunnableConfig) -> dict:
    session = copy.deepcopy(state["session"])
    cart = session["cart"]
    if not session.get("pending_confirm") or not cart:
        return {"reply": "There's nothing waiting for confirmation. Add items, then say place order."}
    db = _db(config)
    address = state["user"].get("address") or ""
    order = Order(user_id=state["user"]["id"], items=json.dumps(cart), total=total(cart), address=address)
    db.add(order)
    db.commit()
    profile_service.bump_frequent_items(db, state["user"]["id"], cart)
    summary = {"id": order.id, "items": cart, "total": order.total, "address": address, "status": order.status}
    session["cart"], session["pending_confirm"] = [], False
    metrics.inc("orders.placed")
    log_event(log, "order_placed", order_id=order.id, total=order.total)
    return {"session": session, "order": summary,
            "reply": f"Your order number {order.id} is confirmed. Total {order.total} rupees, cash on delivery. Enjoy your meal!"}


@_node("deny")
def deny(state: OrderState, config: RunnableConfig) -> dict:
    session = copy.deepcopy(state["session"])
    was_pending = session.get("pending_confirm")
    session["pending_confirm"] = False
    reply = "No problem, I haven't placed the order. You can keep editing your cart." if was_pending else "Okay."
    return {"reply": reply, "session": session}


@_node("set_profile")
def set_profile(state: OrderState, config: RunnableConfig) -> dict:
    ent, db, uid = state["entities"], _db(config), state["user"]["id"]
    if state["intent"] == "set_diet" and ent.get("diet"):
        profile_service.update_profile(db, uid, diet=ent["diet"])
        label = {"veg": "vegetarian", "non-veg": "non-vegetarian", "any": "no dietary restriction"}[ent["diet"]]
        return {"reply": f"Got it, I'll remember you eat {label}." if ent["diet"] != "any"
                else "Got it, I'll remember you have no dietary restriction."}
    if state["intent"] == "set_address" and ent.get("address"):
        profile_service.update_profile(db, uid, address=ent["address"])
        return {"reply": f"Saved. I'll deliver to {ent['address']}. Say place order when you're ready."}
    return {"reply": "Sorry, I didn't catch that."}


@_node("smalltalk")
def smalltalk(state: OrderState, config: RunnableConfig) -> dict:
    intent = state["intent"]
    first = (state["user"].get("name") or "there").split()[0]
    if intent == "greet":
        return {"reply": f"Hi {first}! What would you like to eat? Try add two butter naan, or recommend something spicy."}
    if intent == "help":
        return {"reply": "You can say: add two butter naan, remove the naan, show my cart, recommend something spicy, "
                         "find restaurants near Pune, find recipes for paneer, check Reddit for biryani discussions, "
                         "I'm vegetarian, deliver to my address, or place order."}
    if intent == "thanks":
        return {"reply": "You're welcome! Let me know if you want anything else."}
    text = llm_service.chitchat(state["message"]) if llm_service.available() else None
    return {"reply": text or "Sorry, I didn't catch that. Try add paneer tikka, show my cart, or recommend something."}


@_node("finalize")
def finalize(state: OrderState, config: RunnableConfig) -> dict:
    reply = (state.get("reply") or "Sorry, something went wrong. Please try again.").strip()
    return {"reply": reply[:600]}


# ------------------------------------------------------------------- graph
_HANDLERS = {
    "add_item": add_item, "remove_item": remove_item, "show_cart": show_cart, "clear_cart": clear_cart,
    "recommend": recommend, "show_menu": show_menu, "place_order": place_order, "confirm": confirm,
    "deny": deny, "set_profile": set_profile, "smalltalk": smalltalk,
    "discover_places": discover_places, "find_recipes": find_recipes, "food_buzz": food_buzz,
}
_graph: Any = None


def build_graph():
    g = StateGraph(OrderState)
    g.add_node("understand", understand)
    for name, fn in _HANDLERS.items():
        g.add_node(name, fn)
        g.add_edge(name, "finalize")
    g.add_node("finalize", finalize)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", _route, {name: name for name in _HANDLERS})
    g.add_edge("finalize", END)
    return g.compile()


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_turn(db, user: dict, session: dict, message: str) -> dict:
    """Run one conversational turn and return everything the API layer needs."""
    with span("chat.turn"):
        out = get_graph().invoke(
            {"message": message, "user": user, "session": copy.deepcopy(session), "suggestions": []},
            config={"configurable": {"db": db}},
        )
    metrics.inc("chat.turns")
    return {
        "reply": out["reply"],
        "intent": out["intent"],
        "source": out.get("source", "rule"),
        "session": out["session"],
        "suggestions": out.get("suggestions", []),
        "order": out.get("order"),
    }
