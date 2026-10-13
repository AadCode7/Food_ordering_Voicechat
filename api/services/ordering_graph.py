"""The ordering agent, built with LangGraph.

    START -> understand -> (route by intent) -> <handler> -> finalize -> END

* `understand` uses fast rules first and only falls back to the open-source LLM when needed.
* Handlers are plain, deterministic functions (cart, recommendations, order placement).
* Replies are templated, so the happy path needs zero LLM tokens.
"""
from __future__ import annotations

import copy
import json
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from api.models.orm import Order
from api.services import llm_service, menu_service, profile_service, recommend_service
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
