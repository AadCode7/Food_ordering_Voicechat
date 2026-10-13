import uuid

from utils import nlp
from api.services import external_apis, menu_service, recommend_service


def say(client, headers, sid, text):
    r = client.post("/api/chat", headers=headers, json={"message": text, "session_id": sid})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- pages / health
def test_pages_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/dashboard").status_code == 200
    assert client.get("/static/js/dashboard.js").status_code == 200
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["db"] is True


# ---------------------------------------------------------------- auth
def test_signup_signin_me(client):
    email = f"a_{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/api/auth/signup", json={"name": "Asha K", "email": email.upper(), "password": "password123"})
    assert r.status_code == 201
    assert client.post("/api/auth/signup", json={"name": "Asha", "email": email, "password": "password123"}).status_code == 409
    assert client.post("/api/auth/signin", json={"email": email, "password": "wrongpass1"}).status_code == 401
    t = client.post("/api/auth/signin", json={"email": email, "password": "password123"})
    assert t.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": "Bearer " + t.json()["access_token"]})
    assert me.status_code == 200 and me.json()["email"] == email


def test_validation_and_protection(client):
    assert client.post("/api/auth/signup", json={"name": "x", "email": "bad", "password": "password123"}).status_code == 422
    assert client.post("/api/auth/signup", json={"name": "x", "email": "a@b.co", "password": "short"}).status_code == 422
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 401
    assert client.get("/api/profile").status_code == 401


# ---------------------------------------------------------------- profile
def test_profile_roundtrip(client, auth):
    headers, _ = auth
    p = client.get("/api/profile", headers=headers).json()
    assert p["diet"] == "any" and p["address"] is None
    r = client.put("/api/profile", headers=headers,
                   json={"address": "12 MG Road", "diet": "veg", "spice_level": 2, "cuisines": ["Chinese", " north-indian "]})
    assert r.status_code == 200
    p = client.get("/api/profile", headers=headers).json()
    assert p["address"] == "12 MG Road" and p["diet"] == "veg" and p["spice_level"] == 2
    assert p["cuisines"] == ["chinese", "north-indian"]
    assert client.put("/api/profile", headers=headers, json={"diet": "bogus"}).status_code == 422


# ---------------------------------------------------------------- nlp + menu
def test_nlp_parsing():
    p = nlp.parse("Can you add two butter naan and a paneer tikka to my cart please")
    assert p.intent == "add_item"
    assert p.items == [{"phrase": "butter naan", "qty": 2}, {"phrase": "paneer tikka", "qty": 1}]
    assert nlp.parse("I'm vegetarian").diet == "veg"
    assert nlp.parse("I am non veg").diet == "non-veg"
    assert nlp.parse("deliver to 14 Gandhi Road, Nashik").address == "14 Gandhi Road, Nashik"
    assert nlp.parse("what should I order").intent == "recommend"
    assert nlp.parse("something spicy").intent == "recommend"
    assert nlp.parse("what's in my cart").intent == "show_cart"
    assert nlp.parse("place my order").intent == "place_order"
    assert nlp.parse("yes").intent == "confirm"
    assert nlp.parse("remove the naan").intent == "remove_item"
    assert nlp.parse("find restaurants near Pune").intent == "discover_places"
    assert nlp.parse("find recipes for paneer").intent == "find_recipes"
    assert nlp.parse("what's trending on Reddit about biryani").intent == "food_buzz"


def test_menu_matching():
    assert menu_service.match_item("butter naan")[0]["id"] == "butter-naan"
    assert menu_service.match_item("naan")[0]["id"] == "butter-naan"
    assert menu_service.match_item("biryani", "veg")[0]["id"] == "veg-biryani"
    assert menu_service.match_item("chiken biryani")[0]["id"] == "chicken-biryani"
    assert menu_service.match_item("spaceship")[0] is None


def test_recommend_respects_diet():
    recs = recommend_service.recommend({"diet": "veg", "spice_level": 2, "cuisines": [], "frequent_items": {}}, ["spicy"], limit=8)
    assert recs and all(r["veg"] for r in recs)


# ---------------------------------------------------------------- full ordering flow (LangGraph)
def test_order_flow(client, auth):
    headers, _ = auth
    sid = uuid.uuid4().hex
    assert "Hi" in say(client, headers, sid, "hello")["reply"]
    r = say(client, headers, sid, "add two butter naan and one paneer tikka")
    assert r["intent"] == "add_item" and r["total"] == 2 * 60 + 260 and len(r["cart"]) == 2
    r = say(client, headers, sid, "add a butter naan")
    assert next(c for c in r["cart"] if c["id"] == "butter-naan")["qty"] == 3
    r = say(client, headers, sid, "remove the paneer tikka")
    assert r["total"] == 180 and len(r["cart"]) == 1
    assert say(client, headers, sid, "show my cart")["intent"] == "show_cart"
    # cart survives between requests (short-lived server state)
    assert client.get(f"/api/chat/cart?session_id={sid}", headers=headers).json()["total"] == 180
    # no address yet -> asks for it
    assert "deliver" in say(client, headers, sid, "place my order")["reply"].lower()
    say(client, headers, sid, "deliver to 14 Gandhi Road, Nashik")
    r = say(client, headers, sid, "place my order")
    assert "yes" in r["reply"].lower()
    r = say(client, headers, sid, "yes")
    assert r["order"] and r["order"]["total"] == 180 and r["cart"] == []
    # distilled memory: frequent items updated, no chat history stored
    prof = client.get("/api/profile", headers=headers).json()
    assert prof["frequent_items"] == {"butter-naan": 3}
    assert say(client, headers, sid, "yes")["order"] is None  # nothing left to confirm


def test_veg_user_is_protected(client, auth):
    headers, _ = auth
    sid = uuid.uuid4().hex
    say(client, headers, sid, "I'm vegetarian")
    r = say(client, headers, sid, "add chicken biryani")
    assert r["cart"] == [] and "non-veg" in r["reply"]
    r = say(client, headers, sid, "add biryani")
    assert r["cart"][0]["id"] == "veg-biryani"


def test_recommend_and_menu_and_unknown(client, auth):
    headers, _ = auth
    sid = uuid.uuid4().hex
    r = say(client, headers, sid, "recommend something sweet")
    assert r["intent"] == "recommend" and r["suggestions"]
    assert say(client, headers, sid, "what drinks do you have")["intent"] == "show_menu"
    r = say(client, headers, sid, "tell me about the weather on mars")
    assert r["intent"] == "chitchat" and r["reply"]
    assert say(client, headers, sid, "zzz add flying carpet")["cart"] == []




def test_conversational_discovery_uses_provider_results(client, auth, monkeypatch):
    headers, _ = auth
    sid = uuid.uuid4().hex

    monkeypatch.setattr(external_apis, "google_places", lambda query, limit=5: {
        "source": "google_places", "available": True,
        "results": [{"name": "Sushi Place", "rating": 4.5, "address": "Pune"}],
    })
    monkeypatch.setattr(external_apis, "yelp", lambda term, location, limit=5: {
        "source": "yelp", "available": True,
        "results": [
            {"name": "Sushi Place", "rating": 4.5, "address": "Pune"},
            {"name": "Noodle Spot", "rating": 4.2, "address": "Pune"},
        ],
    })
    monkeypatch.setattr(external_apis, "spoonacular", lambda query, limit=5: {
        "source": "spoonacular", "available": True,
        "results": [{"title": "Paneer Tikka"}, {"title": "Paneer Curry"}],
    })
    monkeypatch.setattr(external_apis, "reddit", lambda query, subreddit="IndianFood", limit=5: {
        "source": "reddit", "available": True,
        "results": [{"title": "Favourite biryani places", "url": "https://www.reddit.com/r/IndianFood/example"}],
    })

    places = say(client, headers, sid, "find restaurants near Pune")
    assert places["intent"] == "discover_places"
    assert "Sushi Place" in places["reply"] and "Noodle Spot" in places["reply"]
    assert places["reply"].count("Sushi Place") == 1

    recipes = say(client, headers, sid, "find recipes for paneer")
    assert recipes["intent"] == "find_recipes" and "Paneer Tikka" in recipes["reply"]

    buzz = say(client, headers, sid, "what's trending on Reddit about biryani")
    assert buzz["intent"] == "food_buzz" and "Favourite biryani places" in buzz["reply"]

def test_sessions_are_isolated(client, auth):
    headers, _ = auth
    other = client.post("/api/auth/signup", json={"name": "Other", "email": f"o_{uuid.uuid4().hex[:6]}@x.com", "password": "password123"}).json()
    oh = {"Authorization": "Bearer " + other["access_token"]}
    sid = uuid.uuid4().hex
    say(client, headers, sid, "add samosa")
    assert client.get(f"/api/chat/cart?session_id={sid}", headers=oh).json()["cart"] == []
    assert client.delete(f"/api/chat/session?session_id={sid}", headers=headers).status_code == 200
    assert client.get(f"/api/chat/cart?session_id={sid}", headers=headers).json()["cart"] == []


def test_chat_input_validation(client, auth):
    headers, _ = auth
    assert client.post("/api/chat", headers=headers, json={"message": ""}).status_code == 422
    assert client.post("/api/chat", headers=headers, json={"message": "hi", "session_id": "bad id!"}).status_code == 422
    assert client.post("/api/chat", headers=headers, json={"message": "x" * 501}).status_code == 422


# ---------------------------------------------------------------- misc endpoints
def test_menu_discover_metrics(client, auth):
    headers, _ = auth
    assert len(client.get("/api/menu").json()["items"]) >= 30
    assert all(i["veg"] for i in client.get("/api/menu?veg_only=true").json()["items"])
    assert client.get("/api/recommendations?tags=spicy", headers=headers).json()["items"]
    d = client.get("/api/discover/places?q=biryani", headers=headers).json()
    assert d["google_places"]["available"] is False and d["yelp"]["available"] is False  # dummy keys
    assert client.get("/api/discover/recipes?q=pasta", headers=headers).json()["available"] is False
    assert client.get("/api/discover/buzz?q=pizza", headers=headers).json()["available"] is False
    m = client.get("/api/metrics", headers=headers).json()
    assert m["counters"].get("chat.turns", 0) >= 0 and "timings_ms" in m
    assert client.get("/api/metrics").status_code == 401
