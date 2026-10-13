(() => {
  if (!getToken()) { location.href = "/"; return; }
  const $ = (id) => document.getElementById(id);
  const sid = sessionStorage.getItem("bv_sid") || randomId();
  sessionStorage.setItem("bv_sid", sid);
  let listening = false, busy = false, recognition = null;

  function addMsg(text, who) {
    const el = document.createElement("div");
    el.className = "msg " + who;
    el.textContent = text;
    $("log").appendChild(el);
    $("log").scrollTop = $("log").scrollHeight;
  }
  function speak(text) {
    if (!$("speak").checked || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-IN";
    window.speechSynthesis.speak(u);
  }
  function renderCart(cart, total) {
    const box = $("cart");
    box.textContent = "";
    if (!cart.length) {
      const d = document.createElement("div"); d.className = "mut"; d.textContent = "Your cart is empty."; box.appendChild(d);
    }
    cart.forEach((l) => {
      const row = document.createElement("div"); row.className = "line";
      const left = document.createElement("span");
      left.textContent = l.qty + " × " + l.name;
      const dot = document.createElement("span"); dot.textContent = l.veg ? " 🟢" : " 🔴"; left.appendChild(dot);
      const right = document.createElement("span"); right.textContent = "₹" + l.price * l.qty;
      row.append(left, right); box.appendChild(row);
    });
    $("total").textContent = "₹" + total;
    $("order").disabled = !cart.length;
  }
  function renderChips(items) {
    const box = $("recs");
    box.textContent = "";
    if (!items.length) { box.textContent = "No suggestions yet."; return; }
    items.forEach((i) => {
      const b = document.createElement("button"); b.className = "chip"; b.type = "button";
      b.textContent = (i.veg ? "🟢 " : "🔴 ") + i.name + " · ₹" + i.price;
      if (i.reason) { const s = document.createElement("small"); s.textContent = "  " + i.reason; b.appendChild(s); }
      b.onclick = () => send("add " + i.name);
      box.appendChild(b);
    });
  }
  function setStatus(t) { $("status").textContent = t; }

  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true; $("send").disabled = true;
    addMsg(text, "me"); $("text").value = "";
    setStatus("Thinking…");
    try {
      const r = await apiFetch("/chat", { method: "POST", body: { message: text, session_id: sid } });
      addMsg(r.reply, "bot"); speak(r.reply);
      renderCart(r.cart, r.total);
      if (r.suggestions && r.suggestions.length) renderChips(r.suggestions);
      if (r.order) loadProfile();
      setStatus("Done in " + r.latency_ms + " ms. Tap the mic to continue.");
    } catch (e) {
      addMsg("⚠️ " + e.message, "bot"); setStatus("Something went wrong.");
    } finally {
      busy = false; $("send").disabled = false;
    }
  }

  // ---- voice input (browser Web Speech API: free, streaming, low latency) ----
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    $("mic").disabled = true;
    setStatus("Voice input isn't supported in this browser (try Chrome or Edge). You can type instead.");
  } else {
    recognition = new SR();
    recognition.lang = "en-IN"; recognition.interimResults = true; recognition.continuous = false;
    recognition.onresult = (ev) => {
      let interim = "", final = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) final += t; else interim += t;
      }
      if (interim) setStatus("Hearing: " + interim);
      if (final) send(final);
    };
    recognition.onerror = (ev) => {
      const msgs = { "not-allowed": "Microphone permission denied.", "no-speech": "I didn't hear anything.", "audio-capture": "No microphone found." };
      setStatus(msgs[ev.error] || "Voice error: " + ev.error);
    };
    recognition.onend = () => { listening = false; $("mic").classList.remove("live"); };
    $("mic").onclick = () => {
      if (listening) { recognition.stop(); return; }
      if ("speechSynthesis" in window) window.speechSynthesis.cancel();
      try { recognition.start(); listening = true; $("mic").classList.add("live"); setStatus("Listening…"); }
      catch (e) { setStatus("Mic is busy, try again."); }
    };
  }

  // ---- profile ----
  async function loadProfile() {
    try {
      const p = await apiFetch("/profile");
      $("address").value = p.address || ""; $("diet").value = p.diet; $("spice").value = String(p.spice_level);
      $("cuisines").value = (p.cuisines || []).join(", ");
    } catch (e) { /* handled in apiFetch */ }
  }
  $("save").onclick = async () => {
    $("saved").textContent = "";
    try {
      await apiFetch("/profile", { method: "PUT", body: {
        address: $("address").value, diet: $("diet").value, spice_level: Number($("spice").value),
        cuisines: $("cuisines").value.split(",").map((s) => s.trim()).filter(Boolean),
      } });
      $("saved").textContent = "Saved ✓";
      loadRecs();
    } catch (e) { $("saved").textContent = ""; addMsg("⚠️ " + e.message, "bot"); }
  };
  async function loadRecs() {
    try { renderChips((await apiFetch("/recommendations?limit=6")).items); } catch (e) { /* ignore */ }
  }

  $("send").onclick = () => send($("text").value);
  $("text").addEventListener("keydown", (e) => { if (e.key === "Enter") send($("text").value); });
  $("order").onclick = () => send("place order");
  $("logout").onclick = async () => {
    try { await apiFetch("/chat/session?session_id=" + sid, { method: "DELETE" }); } catch (e) { /* ignore */ }
    clearToken(); sessionStorage.removeItem("bv_sid"); location.href = "/";
  };

  (async () => {
    try {
      const me = await apiFetch("/auth/me");
      $("hello").textContent = "Hi, " + me.name.split(" ")[0];
      addMsg("Hi " + me.name.split(" ")[0] + "! What would you like to eat today?", "bot");
      const c = await apiFetch("/chat/cart?session_id=" + sid);
      renderCart(c.cart, c.total);
    } catch (e) { /* handled in apiFetch */ }
    loadProfile(); loadRecs();
  })();
})();
